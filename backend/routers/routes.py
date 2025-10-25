# project_path/backend/routers/routes.py

from backend.config import config
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from typing import List, Optional, Dict, Any
from collections import defaultdict
from backend.services.file_processor import FileProcessor
from backend.models.document import DocumentRecord, DocumentElement


router = APIRouter()

# FileProcessor 싱글톤 인스턴스 생성
# 매 요청마다 새로 생성하지 않고 재사용하여 불필요한 초기화 방지
_file_processor_instance = None

def get_file_processor():
    """
    FileProcessor 인스턴스를 반환합니다.
    싱글톤 패턴으로 구현되어 한 번만 생성되고 재사용됩니다.

    Returns:
        FileProcessor: 파일 처리 서비스 인스턴스
    """
    global _file_processor_instance
    if _file_processor_instance is None:
        _file_processor_instance = FileProcessor()
    return _file_processor_instance

@router.post("/upload", response_model=DocumentRecord)
async def upload_file(
    file: UploadFile = File(...),
    processor: FileProcessor = Depends(get_file_processor)
):
    """
    파일을 업로드하고 파싱을 시작합니다.
    - Upstage API를 통해 자동으로 OCR 및 텍스트 추출 수행
    - 이미지 내 텍스트도 자동으로 추출됨
    - 백그라운드에서 비동기로 파싱 진행

    Args:
        file: 업로드할 파일 (PDF, DOCX, PPTX, 이미지 등)

    Returns:
        DocumentRecord: 생성된 문서 레코드 (파싱은 백그라운드에서 진행)
    """
    try:
        file_content = await file.read()
        
        is_valid, error_message = processor.validate_file(file.filename, len(file_content))
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)
        
        # 단순화된 옵션 - 이미지 추출 여부만 실제로 의미있음
        options = {"extract_images": True}
        
        record = await processor.process_file(
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            enhanced_options=options
        )
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """
    문서를 삭제합니다.
    - 업로드된 원본 파일 삭제
    - 파싱된 결과 파일 삭제
    - 메타데이터에서 제거

    Args:
        doc_id: 삭제할 문서 ID

    Returns:
        message: 삭제 완료 메시지
    """
    try:
        success = await processor.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"message": "Document deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@router.get("/analytics/summary")
async def get_analytics_summary(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get system analytics summary"""
    try:
        all_docs = await processor.get_all_documents()
        
        summary = defaultdict(int)
        category_stats = defaultdict(int)
        status_counts = defaultdict(int)
        
        for doc in all_docs:
            summary['total_documents'] += 1
            status_counts[doc.parsing_status] += 1
            
            if doc.is_parsed:
                summary['completed_documents'] += 1
                elements = doc.parsed_data.elements
                summary['total_elements'] += len(elements)
                
                for element in elements:
                    category_stats[element.category] += 1
                    if element.base64_encoding:
                        summary['total_images'] += 1
                    if hasattr(element, '_ocr_enhanced') and element._ocr_enhanced:
                        summary['ocr_enhanced_elements'] += 1

        return {
            "summary": {
                **summary,
                "success_rate": (summary['completed_documents'] / summary['total_documents'] * 100) if summary['total_documents'] > 0 else 0,
            },
            "category_distribution": category_stats,
            "processing_status": status_counts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve analytics: {str(e)}")

@router.get("/documents", response_model=List[DocumentRecord])
async def get_documents(
    status: Optional[str] = Query(None, description="Status filter"),
    has_ocr_enhancement: Optional[bool] = Query(None, description="Filter documents with OCR"),
    limit: int = Query(50, ge=1, le=100, description="Result limit"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get all documents with filtering support"""
    try:
        documents = await processor.get_all_documents()
        
        if status:
            documents = [doc for doc in documents if doc.parsing_status == status]
        
        if has_ocr_enhancement is not None:
            filtered_docs = []
            for doc in documents:
                if doc.parsing_status == 'completed' and doc.parsed_data:
                    has_ocr = any(hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced 
                                for elem in doc.parsed_data.elements)
                    if has_ocr_enhancement == has_ocr:
                        filtered_docs.append(doc)
                elif not has_ocr_enhancement:
                    filtered_docs.append(doc)
            documents = filtered_docs
        
        documents = documents[:limit]
        
        return documents
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document list: {str(e)}")

@router.get("/documents/{doc_id}", response_model=DocumentRecord)
async def get_document(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get specific document"""
    try:
        record = await processor.get_document(doc_id)
        if not record:
            raise HTTPException(status_code=404, detail="Document not found.")
        return record
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get document: {str(e)}")