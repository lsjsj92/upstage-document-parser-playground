# project_path/backend/services/upstage_client.py

import httpx
import aiofiles
from typing import Dict, Any, Optional, List
from pathlib import Path
from backend.config import config  
from backend.models.document import ParsedDocument, DocumentElement, ElementContent, Coordinate
from backend.models.document import DocumentContent
import base64
import asyncio

class UpstageClient:
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.UPSTAGE_API_KEY
        self.base_url = config.UPSTAGE_API_URL
        
        if not self.api_key:
            raise ValueError("Upstage API key is required. Please set UPSTAGE_API_KEY in environment variables.")
            
    async def parse_document_with_hybrid_extraction(self, file_path: Path, extract_images: bool = True) -> ParsedDocument:
        print(f"[UpstageClient] Starting parsing for: {file_path.name}")
        
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
                if parsed_data and parsed_data.elements:
                    for elem in parsed_data.elements:
                        # 이미지가 있고 텍스트가 추출되었으면 OCR 완료로 표시
                        if elem.base64_encoding and elem.content and elem.content.text:
                            setattr(elem, '_ocr_enhanced', True)
                            print(f"[DEBUG] Element {elem.id} already has OCR text: {len(elem.content.text)} chars")
                
                print(f"[UpstageClient] Parsing completed. Total elements: {len(parsed_data.elements) if parsed_data else 0}")
                return parsed_data
                
        except Exception as e:
            print(f"[ERROR] Document parsing failed: {str(e)}")
            raise

    async def parse_document_with_image_extraction(self, file_path: Path, extract_images: bool = True) -> ParsedDocument:
        return await self.parse_document_with_hybrid_extraction(file_path, extract_images)
    
    def _has_table_structure(self, text: str) -> bool:
        """Check if text has table-like structure"""
        indicators = ['|', '\t', '  ', 'row', 'column', 'cell']
        return any(indicator in text.lower() for indicator in indicators)
    
    def _generate_enhanced_html(self, element: DocumentElement, ocr_text: str) -> str:
        """Generate enhanced HTML with both image and extracted text"""
        original_html = element.content.html if element.content else ""
        
        if element.category == 'table':
            return f"""
            <div class="enhanced-table-element">
                <div class="table-image">
                    <img src="data:{element.image_mime_type or 'image/png'};base64,{element.base64_encoding}" alt="Table Image"/>
                </div>
                <div class="extracted-table-content">
                    <h4>Extracted Text:</h4>
                    <pre>{ocr_text}</pre>
                </div>
            </div>
            """
        else:
            return f"""
            <div class="enhanced-element">
                <div class="element-image">
                    <img src="data:{element.image_mime_type or 'image/png'};base64,{element.base64_encoding}" alt="{element.category} Image"/>
                </div>
                <div class="extracted-content">
                    <p>{ocr_text}</p>
                </div>
            </div>
            """
    
    def _generate_enhanced_markdown(self, element: DocumentElement, ocr_text: str) -> str:
        """Generate enhanced Markdown with extracted text"""
        if element.category == 'table':
            # Try to format as table if possible
            table_markdown = self._format_as_markdown_table(ocr_text)
            if table_markdown:
                return f"![Table]() \n\n{table_markdown}"
            else:
                return f"![Table]() \n\n```\n{ocr_text}\n```"
        else:
            return f"![{element.category}]() \n\n{ocr_text}"
    
    def _format_as_markdown_table(self, text: str) -> str:
        """Attempt to format extracted text as Markdown table"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        if len(lines) < 2:
            return ""
        
        try:
            # Simple heuristic table formatting
            formatted_lines = []
            for i, line in enumerate(lines[:5]):  # Limit to first 5 lines
                # Replace multiple spaces/tabs with | separator
                formatted_line = '| ' + ' | '.join(line.split()) + ' |'
                formatted_lines.append(formatted_line)
                
                # Add header separator after first line
                if i == 0:
                    separator = '|' + '---|' * (len(line.split())) + ''
                    formatted_lines.append(separator)
            
            return '\n'.join(formatted_lines)
        except:
            return ""
    def _convert_elements_to_markdown_enhanced(self, elements: List[DocumentElement]) -> str:
        """Convert enhanced elements to markdown with OCR content"""
        if not elements:
            return ""

        sorted_elements = sorted(elements, key=lambda e: (e.page, e.coordinates[0].y if e.coordinates else 0))
        
        markdown_parts = []
        for elem in sorted_elements:
            if elem.content and elem.content.markdown:
                markdown_parts.append(elem.content.markdown)
            elif elem.content and elem.content.text:
                markdown_parts.append(elem.content.text)

        return "\n\n".join(part for part in markdown_parts if part)
    
    async def test_api_connection(self) -> Dict[str, Any]:
        """Test API connection and basic functionality"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        # Create a minimal test request
        test_data = {
            "model": "document-parse"
        }
        
        try:
            # Test with minimal parameters
            timeout = httpx.Timeout(30.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Just test the endpoint without file
                response = await client.post(self.base_url, headers=headers, data=test_data)
                
                return {
                    "status_code": response.status_code,
                    "api_reachable": True,
                    "error": None if response.status_code != 400 else "Expected 400 without file"
                }
                
        except httpx.HTTPStatusError as e:
            return {
                "status_code": e.response.status_code,
                "api_reachable": True,
                "error": e.response.text if hasattr(e.response, 'text') else str(e)
            }
        except Exception as e:
            return {
                "status_code": None,
                "api_reachable": False,
                "error": str(e)
            }

        return await self.parse_document_with_hybrid_extraction(file_path, extract_images)
    
    async def parse_document(self, file_path: Path, **kwargs) -> ParsedDocument:
        """Original parse document method"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            async with aiofiles.open(file_path, 'rb') as file:
                file_content = await file.read()
                
            files = {"document": (file_path.name, file_content, self._get_content_type(file_path))}
            
            data = {"model": "document-parse"}
            data.update(kwargs)
            
            timeout = httpx.Timeout(600.0)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.base_url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                
                return self._parse_response(result)
                
        except Exception as e:
            raise Exception(f"Document parsing failed: {str(e)}")
    
    def _get_content_type(self, file_path: Path) -> str:
        """Get content type from file extension"""
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
        """Parse API response into ParsedDocument"""
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
        """Parse individual element from response"""
        coordinates = []
        coord_data = elem_data.get('coordinates', [])
        
        if coord_data:
            for coord in coord_data:
                if isinstance(coord, dict) and 'x' in coord and 'y' in coord:
                    coordinates.append(Coordinate(x=float(coord['x']), y=float(coord['y'])))
                elif isinstance(coord, list) and len(coord) >= 2:
                    coordinates.append(Coordinate(x=float(coord[0]), y=float(coord[1])))
        
        content_data = elem_data.get('content', {})
        if isinstance(content_data, str):
            content = ElementContent(text=content_data, html='', markdown='')
        else:
            content = ElementContent(
                html=content_data.get('html', ''),
                markdown=content_data.get('markdown', ''),
                text=content_data.get('text', '')
            )
        
        base64_encoding = elem_data.get('base64_encoding')
        if isinstance(base64_encoding, dict):
            base64_encoding = base64_encoding.get('data', '')
        elif not isinstance(base64_encoding, str):
            base64_encoding = None
        
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