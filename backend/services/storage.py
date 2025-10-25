# project_path/backend/services/storage.py

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
import aiofiles
from backend.config import config 
from backend.models.document import DocumentRecord, ParsedDocument

class StorageService:
    """파일 저장 및 문서 기록 관리 서비스"""
    
    def __init__(self):
        # config 인스턴스 사용
        self.uploads_dir = config.UPLOADS_DIR
        self.parsed_dir = config.PARSED_DIR
        self.metadata_file = config.STORAGE_DIR / "metadata.json"
        
        # 초기화 시 디렉토리 생성 보장
        self._ensure_directories()
    
    def _ensure_directories(self):
        """필요한 디렉토리들이 존재하는지 확인하고 없으면 생성"""
        try:
            # 동기적으로 디렉토리 생성
            self.uploads_dir.mkdir(parents=True, exist_ok=True)
            self.parsed_dir.mkdir(parents=True, exist_ok=True)
            config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            
            print(f"[StorageService] 디렉토리 확인/생성 완료:")
            print(f"  - uploads: {self.uploads_dir}")
            print(f"  - parsed: {self.parsed_dir}")
            print(f"  - storage: {config.STORAGE_DIR}")
        except Exception as e:
            print(f"[StorageService] 디렉토리 생성 실패: {e}")
    
    async def save_uploaded_file(self, file_content: bytes, filename: str, content_type: str) -> DocumentRecord:
        """
        업로드된 파일을 저장하고 DocumentRecord를 생성합니다.
        
        Args:
            file_content: 파일 내용
            filename: 원본 파일명
            content_type: 파일 MIME 타입
            
        Returns:
            DocumentRecord: 생성된 문서 레코드
        """
        # 디렉토리 존재 재확인 (파일 저장 직전)
        self._ensure_directories()
        
        # 고유 ID 생성
        doc_id = str(uuid.uuid4())
        file_extension = Path(filename).suffix
        stored_filename = f"{doc_id}{file_extension}"
        file_path = self.uploads_dir / stored_filename
        
        try:
            # 파일 저장
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
            
            print(f"[StorageService] 파일 저장 성공: {file_path}")
            
        except Exception as e:
            print(f"[StorageService] 파일 저장 실패: {e}")
            # 디렉토리 문제일 수 있으므로 한 번 더 시도
            self._ensure_directories()
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(file_content)
        
        # DocumentRecord 생성
        record = DocumentRecord(
            id=doc_id,
            filename=stored_filename,
            original_filename=filename,
            file_path=str(file_path),
            file_size=len(file_content),
            content_type=content_type,
            upload_time=datetime.now(),
            parsing_status="pending"
        )
        
        # 메타데이터 저장
        await self._save_metadata(record)
        
        return record
    
    async def save_parsed_data(self, doc_id: str, parsed_data: ParsedDocument) -> bool:
        """
        파싱된 데이터를 저장합니다.
        
        Args:
            doc_id: 문서 ID
            parsed_data: 파싱된 데이터
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            # 디렉토리 존재 확인
            self._ensure_directories()
            
            # 파싱 결과를 JSON 파일로 저장
            parsed_file_path = self.parsed_dir / f"{doc_id}.json"
            async with aiofiles.open(parsed_file_path, 'w', encoding='utf-8') as f:
                await f.write(parsed_data.model_dump_json(indent=2))

            print(f"[StorageService] 파싱 데이터 저장 성공: {parsed_file_path}")

            # 메타데이터 업데이트
            record = await self.get_document_record(doc_id)
            if record:
                record.parsed_data = parsed_data
                record.parsing_status = "completed"
                await self._save_metadata(record)
                return True
            
            return False
            
        except Exception as e:
            print(f"[StorageService] 파싱 데이터 저장 실패: {e}")
            # 에러 상태로 업데이트
            record = await self.get_document_record(doc_id)
            if record:
                record.parsing_status = "failed"
                record.error_message = str(e)
                await self._save_metadata(record)
            raise e
    
    async def get_document_record(self, doc_id: str) -> Optional[DocumentRecord]:
        """
        문서 레코드를 조회합니다.
        
        Args:
            doc_id: 문서 ID
            
        Returns:
            Optional[DocumentRecord]: 문서 레코드
        """
        metadata = await self._load_metadata()
        record_data = metadata.get(doc_id)
        
        if not record_data:
            return None
        
        record = DocumentRecord(**record_data)
        
        # 파싱 데이터가 완료 상태이면 로드
        if record.parsing_status == "completed":
            parsed_data = await self._load_parsed_data(doc_id)
            if parsed_data:
                record.parsed_data = parsed_data
        
        return record
    
    async def get_all_documents(self) -> List[DocumentRecord]:
        """
        모든 문서 레코드를 조회합니다.
        
        Returns:
            List[DocumentRecord]: 문서 레코드 목록
        """
        metadata = await self._load_metadata()
        records = []
        
        for doc_id in metadata.keys():
            record = await self.get_document_record(doc_id)
            if record:
                records.append(record)
        
        # 업로드 시간 역순으로 정렬
        return sorted(records, key=lambda x: x.upload_time, reverse=True)
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        문서와 관련된 모든 파일을 삭제합니다.
        
        Args:
            doc_id: 문서 ID
            
        Returns:
            bool: 삭제 성공 여부
        """
        try:
            record = await self.get_document_record(doc_id)
            if not record:
                return False
            
            # 업로드된 파일 삭제
            file_path = Path(record.file_path)
            if file_path.exists():
                file_path.unlink()
            
            # 파싱된 파일 삭제
            parsed_file_path = self.parsed_dir / f"{doc_id}.json"
            if parsed_file_path.exists():
                parsed_file_path.unlink()
            
            # 메타데이터에서 제거
            metadata = await self._load_metadata()
            if doc_id in metadata:
                del metadata[doc_id]
                await self._save_metadata_dict(metadata)
            
            return True
            
        except Exception:
            return False
    
    async def _load_metadata(self) -> Dict[str, Any]:
        """메타데이터 파일을 로드합니다."""
        # 메타데이터 파일의 디렉토리도 확인
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.metadata_file.exists():
            return {}
        
        try:
            async with aiofiles.open(self.metadata_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            return {}
    
    async def _save_metadata(self, record: DocumentRecord):
        """단일 문서 레코드의 메타데이터를 저장합니다."""
        metadata = await self._load_metadata()
        # parsed_data는 별도 파일로 저장하므로 메타데이터에서 제외
        record_dict = record.model_dump()
        record_dict.pop('parsed_data', None)
        metadata[record.id] = record_dict
        await self._save_metadata_dict(metadata)
    
    async def _save_metadata_dict(self, metadata: Dict[str, Any]):
        """메타데이터 딕셔너리를 파일로 저장합니다."""
        # 메타데이터 파일의 디렉토리 확인
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
        
        async with aiofiles.open(self.metadata_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(metadata, indent=2, default=str))
    
    async def _load_parsed_data(self, doc_id: str) -> Optional[ParsedDocument]:
        """파싱된 데이터를 로드합니다."""
        parsed_file_path = self.parsed_dir / f"{doc_id}.json"
        
        if not parsed_file_path.exists():
            return None
        
        try:
            async with aiofiles.open(parsed_file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                return ParsedDocument(**data)
        except Exception:
            return None