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
        """
        parsing with a hybrid 4-stage pipeline:
        1. Primary document parsing to get structure and images.
        2. Analyze elements to identify OCR candidates.
        3. Perform targeted OCR on image elements.
        4. Merge OCR results back into the original elements.
        """
        print(f"[UpstageClient] Starting hybrid parsing for: {file_path.name}")
        
        # Stage 1: Primary document parsing with enhanced image extraction
        primary_result = await self._primary_document_parsing(file_path, extract_images)
        
        # Stage 2, 3, 4: Analyze, Enhance with OCR, and Merge results
        if primary_result and primary_result.elements:
            enhanced_elements = await self._enhance_elements_with_ocr(primary_result.elements)
            primary_result.elements = enhanced_elements
        
        print(f"[UpstageClient] Hybrid parsing completed. Total elements: {len(primary_result.elements) if primary_result else 0}")
        return primary_result

    async def _primary_document_parsing(self, file_path: Path, extract_images: bool = True) -> ParsedDocument:
        """Helper for Stage 1: Calls document-parse API to get base structure and images."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            async with aiofiles.open(file_path, 'rb') as file:
                file_content = await file.read()
                
            files = {"document": (file_path.name, file_content, self._get_content_type(file_path))}
            
            data = {
                "model": "document-parse",
                "ocr": "force"
            }
            
            if extract_images:
                # Request base64 for all categories that might contain important text
                data["base64_encoding"] = "['table', 'figure', 'chart', 'equation']"
            
            timeout = httpx.Timeout(600.0)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.base_url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                
                print(f"[DEBUG] Primary parsing - Elements with images: {len([e for e in result.get('elements', []) if e.get('base64_encoding')])}")
                return self._parse_response_enhanced(result)
                
        except Exception as e:
            print(f"[ERROR] Primary document parsing failed: {str(e)}")
            raise

    async def _enhance_elements_with_ocr(self, elements: List[DocumentElement]) -> List[DocumentElement]:
        """Helper for Stage 2 & 3: Identifies OCR candidates and runs OCR tasks concurrently."""
        ocr_tasks = []
        elements_to_keep = []

        for element in elements:
            # Stage 2: Identify OCR candidates. Strategy: Enhance ALL elements with an image.
            if self._should_enhance_element_with_ocr(element):
                print(f"[DEBUG] Scheduling OCR enhancement for element {element.id} (category: {element.category})")
                ocr_tasks.append(self._enhance_single_element_with_ocr(element))
            else:
                elements_to_keep.append(element)
        
        if not ocr_tasks:
            return elements_to_keep

        # Stage 3: Process OCR tasks concurrently
        print(f"[DEBUG] Processing {len(ocr_tasks)} OCR enhancement task")
        semaphore = asyncio.Semaphore(5)  # Limit concurrent API calls to 5

        async def bounded_ocr_task(task):
            async with semaphore:
                return await task
        
        bounded_tasks = [bounded_ocr_task(task) for task in ocr_tasks]
        ocr_results = await asyncio.gather(*bounded_tasks, return_exceptions=True)
        
        enhanced_elements = []
        for result in ocr_results:
            if isinstance(result, DocumentElement):
                enhanced_elements.append(result)
            elif isinstance(result, Exception):
                print(f"[WARNING] An OCR enhancement task failed: {result}")
        
        # Combine original elements with enhanced ones and sort by ID to maintain order
        final_elements = elements_to_keep + enhanced_elements
        final_elements.sort(key=lambda x: x.id)
        
        total_enhanced = len([e for e in final_elements if hasattr(e, '_ocr_enhanced') and e._ocr_enhanced])
        print(f"[DEBUG] OCR enhancement completed. Total enhanced elements: {total_enhanced}")
        
        return final_elements

    def _should_enhance_element_with_ocr(self, element: DocumentElement) -> bool:
        """Determines if an element is a candidate for OCR enhancement."""
        return bool(element.base64_encoding)

    async def _enhance_single_element_with_ocr(self, element: DocumentElement) -> DocumentElement:
        """Helper for Stage 4: Performs OCR and merges the result for a single element."""
        try:
            image_data = base64.b64decode(element.base64_encoding)
            
            # Call the specialized OCR model
            ocr_result_text = await self._perform_ocr_on_image_data(image_data)
            
            if ocr_result_text:
                print(f"[DEBUG] OCR extracted {len(ocr_result_text)} chars for element {element.id}")
                
                # Merge the OCR text with existing content
                element.content.text = self._merge_text_content(
                    original_text=element.content.text, 
                    ocr_text=ocr_result_text
                )
                # You can also enhance html and markdown here if needed
                element.content.markdown = f"![{element.category} Image Content]\n\n{ocr_result_text}"

                # Add a flag to track that this element was enhanced
                setattr(element, '_ocr_enhanced', True)
            else:
                setattr(element, '_ocr_enhanced', False)

            return element
            
        except Exception as e:
            print(f"[WARNING] OCR enhancement failed for element {element.id}: {e}")
            setattr(element, '_ocr_enhanced', False)
            return element

    async def _perform_ocr_on_image_data(self, image_data: bytes) -> Optional[str]:
        """Calls the Upstage OCR API on raw image data."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        try:
            files = {"document": ("image.png", image_data, "image/png")}
            # OCR 활용
            data = {"model": "ocr"}
            
            timeout = httpx.Timeout(120.0)
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.base_url, headers=headers, files=files, data=data)
                response.raise_for_status()
                
                result = response.json()
                return result.get('text', '').strip()
                
        except Exception as e:
            print(f"[WARNING] OCR API call failed: {e}")
            return None

    def _merge_text_content(self, original_text: str, ocr_text: str) -> str:
        """Intelligently merges original and OCR text."""
        original_clean = original_text.strip() if original_text else ""
        ocr_clean = ocr_text.strip() if ocr_text else ""
        
        if len(ocr_clean) > 10:
            return ocr_clean

        return original_clean

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
                
                return self._parse_response_enhanced(result)
                
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
    
    def _parse_response_enhanced(self, response_data: Dict[str, Any]) -> ParsedDocument:
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