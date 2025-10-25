# project_path/backend/services/upstage_client.py

import httpx
import aiofiles
from typing import Dict, Any, Optional, List
from pathlib import Path
from backend.config import config
from backend.models.document import ParsedDocument, DocumentElement, ElementContent, Coordinate
from backend.models.document import DocumentContent
import base64

class UpstageClient:
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.UPSTAGE_API_KEY
        self.base_url = config.UPSTAGE_API_URL
        
        if not self.api_key:
            raise ValueError("Upstage API key is required. Please set UPSTAGE_API_KEY in environment variables.")
            
    async def parse_document_with_hybrid_extraction(self, file_path: Path, extract_images: bool = True) -> ParsedDocument:
        """
        Upstage API를 사용하여 문서를 파싱합니다.

        단일 API 호출로 전체 문서를 처리:
        - 모든 페이지를 한 번에 파싱
        - OCR 자동 적용 (force mode)
        - 이미지 추출 (table, figure, chart, equation)

        Args:
            file_path: 파싱할 파일 경로
            extract_images: 이미지 Base64 인코딩 추출 여부

        Returns:
            ParsedDocument: 파싱된 문서 객체 (모든 페이지 포함)
        """
        print(f"[UpstageClient] Starting document parsing: {file_path.name}")
        print(f"[UpstageClient] Calling Upstage API (single request for entire document)...")

        # 단일 API 호출로 모든 처리 완료
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            async with aiofiles.open(file_path, 'rb') as file:
                file_content = await file.read()
                
            files = {"document": (file_path.name, file_content, self._get_content_type(file_path))}
            
            data = {
                "model": "document-parse",
                "ocr": "force"  # 이것만으로 충분! API가 모든 OCR 처리
            }
            
            if extract_images:
                data["base64_encoding"] = "['table', 'figure', 'chart', 'equation']"
            
            timeout = httpx.Timeout(600.0)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.base_url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                
                parsed_data = self._parse_response(result)
                
                # OCR이 이미 적용된 이미지 요소들에 플래그 설정
                ocr_enhanced_count = 0
                if parsed_data and parsed_data.elements:
                    for elem in parsed_data.elements:
                        # 이미지가 있고 텍스트가 추출되었으면 OCR 완료로 표시
                        if elem.base64_encoding and elem.content and elem.content.text:
                            setattr(elem, '_ocr_enhanced', True)
                            ocr_enhanced_count += 1

                print(f"[UpstageClient] Parsing completed successfully!")
                print(f"[UpstageClient] Total elements: {len(parsed_data.elements) if parsed_data else 0}")
                print(f"[UpstageClient] OCR enhanced elements: {ocr_enhanced_count}")
                return parsed_data

        except Exception as e:
            print(f"[ERROR] Document parsing failed: {str(e)}")
            raise

    def _get_content_type(self, file_path: Path) -> str:
        """
        파일 확장자로부터 MIME 타입을 결정합니다.

        Args:
            file_path: 파일 경로

        Returns:
            str: MIME 타입 (예: 'application/pdf', 'image/jpeg')
        """
        extension = file_path.suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.heic': 'image/heic',
            '.webp': 'image/webp'
        }
        return content_types.get(extension, 'application/octet-stream')
    
    def _parse_response(self, response_data: Dict[str, Any]) -> ParsedDocument:
        """
        Upstage API 응답을 ParsedDocument 객체로 변환합니다.

        Args:
            response_data: Upstage API로부터 받은 JSON 응답

        Returns:
            ParsedDocument: 파싱된 문서 객체

        Raises:
            Exception: 응답 파싱 중 오류 발생 시
        """
        try:
            elements = []
            
            if 'elements' in response_data and isinstance(response_data['elements'], list):
                for elem_data in response_data['elements']:
                    elements.append(self._parse_element(elem_data))
            elif 'content' in response_data:
                content_data = response_data.get('content', {})
                element = DocumentElement(
                    id=1,
                    category='document',
                    content=ElementContent(
                        html=content_data.get('html', ''),
                        markdown=content_data.get('markdown', ''),
                        text=content_data.get('text', str(content_data))
                    ),
                    coordinates=[],
                    page=1,
                    base64_encoding=None
                )
                elements = [element]
            
            content_data = response_data.get('content', {})
            if isinstance(content_data, str):
                document_content = DocumentContent(html='', markdown='', text=content_data)
            else:
                document_content = DocumentContent(
                    html=content_data.get('html', ''),
                    markdown=content_data.get('markdown', ''),
                    text=content_data.get('text', '')
                )
            
            return ParsedDocument(
                api=response_data.get('api', 'upstage-document-parse'),
                model=response_data.get('model', 'document-parse'),
                content=document_content,
                elements=elements,
                usage=response_data.get('usage', {})
            )
            
        except Exception as e:
            raise Exception(f"Response parsing failed: {str(e)}. Response: {response_data}")
    
    def _parse_element(self, elem_data: Dict[str, Any]) -> DocumentElement:
        """
        API 응답의 개별 요소를 DocumentElement 객체로 변환합니다.

        Args:
            elem_data: 요소 데이터 딕셔너리

        Returns:
            DocumentElement: 변환된 문서 요소 객체
        """
        # 좌표 정보 파싱 (4개의 꼭지점)
        coordinates = []
        coord_data = elem_data.get('coordinates', [])
        
        if coord_data:
            for coord in coord_data:
                # 좌표가 딕셔너리 형태 {'x': ..., 'y': ...}
                if isinstance(coord, dict) and 'x' in coord and 'y' in coord:
                    coordinates.append(Coordinate(x=float(coord['x']), y=float(coord['y'])))
                # 좌표가 리스트 형태 [x, y]
                elif isinstance(coord, list) and len(coord) >= 2:
                    coordinates.append(Coordinate(x=float(coord[0]), y=float(coord[1])))

        # 콘텐츠 정보 파싱 (html, markdown, text)
        content_data = elem_data.get('content', {})
        if isinstance(content_data, str):
            content = ElementContent(text=content_data, html='', markdown='')
        else:
            content = ElementContent(
                html=content_data.get('html', ''),
                markdown=content_data.get('markdown', ''),
                text=content_data.get('text', '')
            )

        # Base64 인코딩된 이미지 데이터 처리
        # API 응답 형식이 다양할 수 있으므로 여러 형태를 처리
        base64_encoding = elem_data.get('base64_encoding')
        if isinstance(base64_encoding, dict):
            # 딕셔너리 형태: {'data': 'base64string...'}
            base64_encoding = base64_encoding.get('data', '')
        elif not isinstance(base64_encoding, str):
            # 문자열이 아닌 경우 None 처리
            base64_encoding = None

        # 빈 문자열은 None으로 변환
        if base64_encoding == '':
            base64_encoding = None
        
        return DocumentElement(
            id=elem_data.get('id', 0),
            category=elem_data.get('category', 'unknown'),
            content=content,
            coordinates=coordinates,
            page=elem_data.get('page', 1),
            base64_encoding=base64_encoding
        )