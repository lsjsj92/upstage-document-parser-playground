# project_path/backend/services/file_processor.py

import asyncio
import html2text
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from collections import defaultdict
from backend.models.document import DocumentRecord, DocumentElement, ElementContent
from backend.services.upstage_client import UpstageClient
from backend.services.storage import StorageService
from backend.config import config
from backend.utils.helpers import get_image_mime_type_from_base64

class FileProcessor:

    def __init__(self):
        """
        FileProcessor를 초기화합니다.
        - Upstage API 클라이언트 생성
        - 스토리지 서비스 초기화
        - Markdown 변환기 설정

        Note: 싱글톤 패턴으로 사용되므로 애플리케이션 실행 중 1번만 초기화됩니다.
        """
        # 디렉토리 존재 확인 및 생성
        config.ensure_directories_exist()

        self.upstage_client = UpstageClient()
        self.storage_service = StorageService()
        self.markdown_converter = html2text.HTML2Text()
        self.markdown_converter.ignore_links = True
        self.markdown_converter.body_width = 0

        print(f"[FileProcessor] Initialized with hybrid parsing capabilities")
        print(f"[FileProcessor] Storage directory: {config.STORAGE_DIR}")
    
    async def process_file(self, file_content: bytes, filename: str, content_type: str, 
                         enhanced_options: Optional[Dict[str, Any]] = None) -> DocumentRecord:
        """파일 파싱처리"""
        record = await self.storage_service.save_uploaded_file(
            file_content, filename, content_type
        )
        
        default_options = {
            "extract_images": True, 
            "hybrid_parsing": True,
        }
        
        if enhanced_options:
            default_options.update(enhanced_options)
        
        asyncio.create_task(self._parse_document_hybrid_async(record, default_options))
        
        return record
    
    def _convert_elements_to_markdown(self, elements: list[DocumentElement]) -> str:
        """문서 요소들을 논리적 순서에 따라 Markdown 문자열로 변환"""
        if not elements:
            return ""

        sorted_elements = sorted(elements, key=lambda e: (e.page, e.coordinates[0].y if e.coordinates else 0))
        
        markdown_parts = []
        for elem in sorted_elements:
            if (hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced) or elem.category == 'composite_table':
                if elem.content and elem.content.markdown:
                    markdown_parts.append(elem.content.markdown)
                elif elem.content and elem.content.text:
                    markdown_parts.append(elem.content.text)
            else:
                html_content = elem.content.html
                if html_content:
                    markdown_content = self.markdown_converter.handle(html_content).strip()
                    elem.content.markdown = markdown_content
                    markdown_parts.append(markdown_content)

        return "\n\n".join(part for part in markdown_parts if part)
    
    async def _parse_document_hybrid_async(self, record: DocumentRecord, options: Dict[str, Any]):
        """백그라운드 문서 파싱"""
        try:
            await self._update_parsing_status(record.id, "processing")
            
            file_path = Path(record.file_path)
            
            # Always use the new hybrid parsing method
            print(f"[FileProcessor] Starting hybrid parsing for {record.original_filename}")
            parsed_data = await self.upstage_client.parse_document_with_hybrid_extraction(
                file_path=file_path,
                extract_images=options.get("extract_images", True)
            )
            
            if parsed_data and parsed_data.elements:
                # Add MIME type to all image elements
                for elem in parsed_data.elements:
                    if elem.base64_encoding:
                        elem.image_mime_type = get_image_mime_type_from_base64(elem.base64_encoding)
                
                # The composite element analysis can now work with OCR-enhanced data
                if self._is_complex_content_pattern(parsed_data.elements):
                    enhanced_elements = self._analyze_and_enhance_elements(parsed_data.elements)
                    parsed_data.elements = enhanced_elements

                # Generate a complete markdown document from the final, enhanced elements
                full_markdown = self._convert_elements_to_markdown(parsed_data.elements)
                parsed_data.content.markdown = full_markdown
                
                stats = self._generate_parsing_statistics(parsed_data.elements)
                print(f"[FileProcessor] Parsing completed. {stats}")
            
            await self.storage_service.save_parsed_data(record.id, parsed_data)
            
        except Exception as e:
            await self._update_parsing_status(record.id, "failed", str(e))
            print(f"파싱 실패 (ID: {record.id}): {str(e)}")
    
    def _generate_parsing_statistics(self, elements: List[DocumentElement]) -> str:
        """Updated statistics to include OCR info."""
        total_elements = len(elements)
        image_elements = len([e for e in elements if e.base64_encoding])
        ocr_enhanced = len([e for e in elements if hasattr(e, '_ocr_enhanced') and e._ocr_enhanced])
        return f"Total Elements: {total_elements}, Image Elements: {image_elements}, OCR Enhanced: {ocr_enhanced}"

    async def _update_parsing_status(self, doc_id: str, status: str, error_message: Optional[str] = None):
        """Update parsing status"""
        record = await self.storage_service.get_document_record(doc_id)
        if record:
            record.parsing_status = status
            if error_message:
                record.error_message = error_message
            await self.storage_service._save_metadata(record)

    async def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        """Get document record"""
        return await self.storage_service.get_document_record(doc_id)
    
    async def get_all_documents(self) -> list[DocumentRecord]:
        """Get all document records"""
        return await self.storage_service.get_all_documents()
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete document"""
        return await self.storage_service.delete_document(doc_id)
    
    def validate_file(self, filename: str, file_size: int) -> tuple[bool, str]:
        """
        Validate file
        
        Args:
            filename: File name
            file_size: File size in bytes
            
        Returns:
            tuple[bool, str]: (validity, error_message)
        """
        
        # Check file extension
        file_path = Path(filename)
        allowed_extensions = [".pdf", ".docx", ".pptx", ".xlsx", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic", ".webp"]
        if file_path.suffix.lower() not in allowed_extensions:
            return False, f"Unsupported file format. Supported formats: {', '.join(allowed_extensions)}"
        
        # Check file size
        if file_size > config.MAX_FILE_SIZE:
            max_size_mb = config.MAX_FILE_SIZE // (1024 * 1024)
            return False, f"File too large. Maximum size: {max_size_mb}MB"
        
        # Check minimum size
        if file_size < 100:  # Less than 100 bytes
            return False, "File too small. Please check if it's a valid document."
        
        return True, ""

    def _analyze_and_enhance_elements(self, elements: List[DocumentElement]) -> List[DocumentElement]:
        """
        기존 파싱된 요소들을 분석하여 복합 구조를 감지하고 개선된 요소로 변환
        """
        if not elements:
            return elements
        
        enhanced_elements = []
        processed_element_ids = set()
        
        # 페이지별로 그룹화하여 처리
        pages = {}
        for elem in elements:
            page = elem.page
            if page not in pages:
                pages[page] = []
            pages[page].append(elem)
        
        for page_num, page_elements in pages.items():
            page_enhanced = self._process_page_elements(page_elements, processed_element_ids)
            enhanced_elements.extend(page_enhanced)
        
        return enhanced_elements

    def _process_page_elements(self, page_elements: List[DocumentElement], processed_ids: set) -> List[DocumentElement]:
        """페이지 내 요소들을 분석하여 복합 구조 감지"""
        enhanced_elements = []
        
        # 이미지 요소들을 기준으로 복합 구조 탐지 (OCR enhanced 요소 포함)
        image_elements = [elem for elem in page_elements if elem.base64_encoding and elem.id not in processed_ids]
        
        for img_elem in image_elements:
            # 이미지 요소 주변의 텍스트 요소들 찾기
            related_text_elements = self._find_spatially_related_elements(img_elem, page_elements)
            
            if related_text_elements:
                # 복합 테이블 구조로 변환
                composite_element = self._create_enhanced_table_element(img_elem, related_text_elements)
                enhanced_elements.append(composite_element)
                
                # 처리된 요소들을 마킹
                processed_ids.add(img_elem.id)
                for text_elem in related_text_elements:
                    processed_ids.add(text_elem.id)
            else:
                # 관련 텍스트가 없으면 원본 유지
                enhanced_elements.append(img_elem)
                processed_ids.add(img_elem.id)
        
        # 처리되지 않은 요소들 추가
        for elem in page_elements:
            if elem.id not in processed_ids:
                enhanced_elements.append(elem)
        
        return enhanced_elements

    def _find_spatially_related_elements(self, image_element: DocumentElement, all_elements: List[DocumentElement]) -> List[DocumentElement]:
        """공간적 관계를 기반으로 관련 요소들을 찾음"""
        if not image_element.coordinates:
            return []
        
        related_elements = []
        img_bbox = image_element.bounding_box
        
        # 이미지와 같은 행 또는 인접한 영역의 텍스트 요소들 찾기
        for elem in all_elements:
            if (elem.id != image_element.id and 
                elem.coordinates and 
                elem.category in ['paragraph', 'text', 'caption'] and
                elem.content and elem.content.text.strip()):
                
                elem_bbox = elem.bounding_box
                
                # 수직적 근접성 체크 (같은 행 또는 가까운 행)
                vertical_distance = abs(elem_bbox.top_left.y - img_bbox.top_left.y)
                max_vertical_threshold = max(img_bbox.height, 50)  # 이미지 높이 또는 최소 50px
                
                # 수평적 관계 체크 (이미지 우측 또는 전체 영역)
                is_right_of_image = elem_bbox.top_left.x > img_bbox.top_left.x
                
                if vertical_distance <= max_vertical_threshold and is_right_of_image:
                    related_elements.append(elem)
        
        # Y 좌표 기준으로 정렬하여 읽기 순서 유지
        related_elements.sort(key=lambda e: e.coordinates[0].y if e.coordinates else 0)
        
        return related_elements

    def _create_enhanced_table_element(self, image_element: DocumentElement, text_elements: List[DocumentElement]) -> DocumentElement:
        """이미지와 텍스트를 결합한 향상된 테이블 요소 생성"""
        
        # Combine text from adjacent elements
        combined_text_parts = []
        for text_elem in text_elements:
            if text_elem.content and text_elem.content.text.strip():
                combined_text_parts.append(text_elem.content.text.strip())

        # IMPORTANT: Use the image's own OCR-extracted text as the primary source of truth.
        image_text = ""
        if hasattr(image_element, '_ocr_enhanced') and image_element._ocr_enhanced and image_element.content.text:
            image_text = image_element.content.text.strip()
        
        # Merge texts: image's text first, then adjacent elements' text.
        final_text = image_text
        if combined_text_parts:
            final_text += "\n" + "\n".join(combined_text_parts)
        
        final_html = f"""
        <div class="composite-element hybrid-enhanced">
            <div class="image-cell">
                <img src="data:{image_element.image_mime_type or "image/png"};base64,{image_element.base64_encoding}" alt="Composite Image"/>
            </div>
            <div class="text-cell">
                <h4>Extracted Content (OCR Enhanced)</h4>
                <pre>{final_text}</pre>
            </div>
        </div>
        """
        final_markdown = f"![Composite Image]\n\n**Extracted Content:**\n```\n{final_text}\n```"

        # Create a new composite element
        composite_element = DocumentElement(
            id=image_element.id,
            category='composite_table', # New category for these special elements
            content=ElementContent(html=final_html, markdown=final_markdown, text=final_text),
            coordinates=image_element.coordinates, # Use original image coordinates
            page=image_element.page,
            base64_encoding=image_element.base64_encoding,
            image_mime_type=image_element.image_mime_type
        )
        
        # Preserve the OCR flag
        if hasattr(image_element, '_ocr_enhanced'):
            setattr(composite_element, '_ocr_enhanced', image_element._ocr_enhanced)
        
        return composite_element

    def _is_complex_content_pattern(self, elements: List[DocumentElement]) -> bool:
        """복합 패턴 감지"""
        has_images = any(elem.base64_encoding for elem in elements)
        has_text = any(elem.content and elem.content.text for elem in elements)
        # If there are images and text on the same page, it's worth analyzing for composite structures.
        return has_images and has_text