# project_path/backend/routers/routes.py
import aiofiles
from backend.config import config
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse
from typing import List, Optional, Dict, Any
from collections import defaultdict
from backend.services.file_processor import FileProcessor
from backend.models.document import DocumentRecord, DocumentElement


router = APIRouter()

def get_file_processor():
    return FileProcessor()

@router.post("/upload", response_model=DocumentRecord)
async def upload_file(
    file: UploadFile = File(...),
    processor: FileProcessor = Depends(get_file_processor)
):
    """
    Upload file for hybrid parsing. OCR text extraction from images is enabled by default.
    """
    try:
        file_content = await file.read()
        
        is_valid, error_message = processor.validate_file(file.filename, len(file_content))
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_message)
        
        # Options are now simplified as hybrid parsing is the default in the processor
        enhanced_options = {"extract_images": True}
        
        record = await processor.process_file(
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            enhanced_options=enhanced_options
        )
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")

@router.get("/documents/{doc_id}/statistics")
async def get_document_statistics(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get document parsing statistics"""
    try:
        stats = await processor.get_parsing_statistics(doc_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Document statistics not found.")
        return stats
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")

@router.get("/documents/{doc_id}/images")
async def get_document_images(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get images extracted from document with text extraction information"""
    try:
        images = await processor.extract_images_from_document(doc_id)
        
        return {
            "document_id": doc_id,
            "total_images": len(images),
            "images": images
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract images: {str(e)}")

@router.post("/documents/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Reprocess document with OCR text extraction"""
    try:
        enhanced_options = {
            "extract_images": True,
            "ocr_mode": "force",
            "coordinate_mode": True,
            "split_mode": "element",
            "hybrid_parsing": True,
            "ocr_enhancement": True
        }
        
        success = await processor.reprocess_document_with_enhanced_settings(doc_id, enhanced_options)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or reprocessing failed.")
        
        return {
            "message": "Document reprocessing started with OCR text extraction.", 
            "document_id": doc_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reprocessing failed: {str(e)}")

@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Delete document"""
    try:
        success = await processor.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"message": "Document deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")

@router.get("/documents/{doc_id}/elements")
async def get_document_elements(
    doc_id: str,
    page: Optional[int] = Query(None, description="Filter by page number"),
    category: Optional[str] = Query(None, description="Filter by category"),
    ocr_enhanced: Optional[bool] = Query(None, description="Filter for OCR enhanced elements"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get document elements with enhanced filtering, including OCR information."""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="Parsed document not found.")
        
        elements = record.parsed_data.elements
        
        # Apply filters
        if page is not None:
            elements = [elem for elem in elements if elem.page == page]
        
        if category:
            elements = [elem for elem in elements if elem.category == category]
        
        if ocr_enhanced is not None:
            elements = [
                elem for elem in elements 
                if (hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced) == ocr_enhanced
            ]
        
        # Add ocr_enhanced flag to the response for each element
        enhanced_elements_response = []
        for elem in elements:
            elem_dict = elem.model_dump()
            elem_dict['ocr_enhanced'] = hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced
            enhanced_elements_response.append(elem_dict)
            
        ocr_enhanced_count = sum(1 for e in enhanced_elements_response if e.get('ocr_enhanced'))

        return {
            "document_id": doc_id,
            "filters": {
                "page": page,
                "category": category,
                "ocr_enhanced": ocr_enhanced
            },
            "total_elements": len(enhanced_elements_response),
            "ocr_enhanced_count": ocr_enhanced_count,
            "elements": enhanced_elements_response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve elements: {str(e)}")

@router.get("/documents/{doc_id}/hybrid-analysis")
async def get_hybrid_analysis(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get a summary of hybrid parsing and OCR enhancement results for a document."""
    try:
        stats = await processor.get_parsing_statistics(doc_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Document statistics not found.")
        
        total_elements = stats.get('total_elements', 0)
        ocr_elements = stats.get('ocr_enhanced_elements', 0)
        image_elements = stats.get('elements_with_images', 0)
        composite_elements = stats.get('elements_by_category', {}).get('composite_table', 0)

        return {
            "document_id": doc_id,
            "ocr_enhanced_elements": {
                "count": ocr_elements,
                "percentage": (ocr_elements / total_elements * 100) if total_elements > 0 else 0,
                "categories": [cat for cat, count in stats.get('elements_by_category', {}).items() if count > 0] # Simplified for example
            },
            "composite_elements": {
                "count": composite_elements,
                "percentage": (composite_elements / total_elements * 100) if total_elements > 0 else 0
            },
            "enhancement_effectiveness": {
                "text_extraction_rate": (ocr_elements / image_elements * 100) if image_elements > 0 else 0,
                "images_with_extracted_text": ocr_elements,
                "total_images": image_elements
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve hybrid analysis: {str(e)}")

@router.get("/documents/{doc_id}/markdown", response_class=PlainTextResponse)
async def get_document_markdown(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """파싱된 문서의 전체 콘텐츠를 Markdown으로 가져옵니다 (OCR 향상 포함)."""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="파싱된 문서를 찾을 수 없습니다.")
        
        markdown_content = record.parsed_data.content.markdown
        if not markdown_content:
            return "이 문서에 사용 가능한 Markdown 콘텐츠가 없습니다."

        return PlainTextResponse(content=markdown_content, media_type="text/markdown")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Markdown 조회 실패: {str(e)}")

@router.get("/queue/status")
async def get_queue_status(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get processing queue status with hybrid parsing information"""
    try:
        status = await processor.get_processing_queue_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve queue status: {str(e)}")

@router.get("/health")
async def health_check():
    """System health check with hybrid parsing features"""
    return {
        "status": "healthy",
        "features": [
            "hybrid_parsing",
            "ocr_text_extraction",
            "image_extraction", 
            "coordinate_preservation",
            "bounding_box_integration",
            "table_text_enhancement",
            "chart_text_enhancement"
        ]
    }

@router.get("/analytics/summary")
async def get_analytics_summary(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get system analytics summary with hybrid parsing metrics."""
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
                doc_has_ocr = False
                elements = doc.parsed_data.elements
                summary['total_elements'] += len(elements)
                
                for element in elements:
                    category_stats[element.category] += 1
                    if element.base64_encoding:
                        summary['total_images'] += 1
                    if hasattr(element, '_ocr_enhanced') and element._ocr_enhanced:
                        summary['ocr_enhanced_elements'] += 1
                        doc_has_ocr = True
                
                if doc_has_ocr:
                    summary['hybrid_processed_documents'] += 1

        return {
            "summary": {
                **summary,
                "success_rate": (summary['completed_documents'] / summary['total_documents'] * 100) if summary['total_documents'] > 0 else 0,
            },
            "category_distribution": category_stats,
            "processing_status": status_counts,
            "hybrid_parsing_metrics": {
                "ocr_enhancement_coverage": (summary['hybrid_processed_documents'] / summary['completed_documents'] * 100) if summary['completed_documents'] > 0 else 0,
                "image_text_extraction_rate": (summary['ocr_enhanced_elements'] / summary['total_images'] * 100) if summary['total_images'] > 0 else 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve analytics: {str(e)}")

@router.get("/documents/{doc_id}/preview")
async def get_document_preview(
    doc_id: str,
    page: int = Query(1, description="Page number to preview"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get document preview for specific page with hybrid parsing information"""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="Parsed document not found.")
        
        page_elements = [elem for elem in record.parsed_data.elements if elem.page == page]
        
        # Enhanced preview information
        ocr_enhanced_elements = [elem for elem in page_elements if hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced]
        image_elements = [elem for elem in page_elements if elem.base64_encoding]
        
        return {
            "document_id": doc_id,
            "page": page,
            "total_pages": record.total_pages,
            "elements": [elem.model_dump() for elem in page_elements],
            "has_images": len(image_elements) > 0,
            "element_count": len(page_elements),
            "ocr_enhanced_count": len(ocr_enhanced_elements),
            "image_count": len(image_elements),
            "hybrid_parsing_applied": len(ocr_enhanced_elements) > 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve preview: {str(e)}")

@router.post("/upload/batch", response_model=List[DocumentRecord])
async def upload_files_batch(
    files: List[UploadFile] = File(...),
    enable_hybrid: bool = Query(True, description="Enable hybrid parsing for batch"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Batch file upload with hybrid parsing settings"""
    try:
        file_list = []
        for file in files:
            file_content = await file.read()
            
            # Individual file validation
            is_valid, error_message = processor.validate_file(file.filename, len(file_content))
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"{file.filename}: {error_message}")
            
            file_list.append({
                'content': file_content,
                'filename': file.filename,
                'content_type': file.content_type or "application/octet-stream"
            })
        
        # Enhanced options for all files
        enhanced_options = {
            "extract_images": True,
            "ocr_mode": "force",
            "coordinate_mode": True,
            "split_mode": "element",
            "hybrid_parsing": enable_hybrid,
            "ocr_enhancement": enable_hybrid,
            "table_text_extraction": True,
            "chart_text_extraction": True
        }
        
        # Batch processing
        records = await processor.process_file_batch(file_list, enhanced_options)
        return records
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {str(e)}")

@router.get("/documents", response_model=List[DocumentRecord])
async def get_documents(
    status: Optional[str] = Query(None, description="Status filter (completed/processing/failed/pending)"),
    has_ocr_enhancement: Optional[bool] = Query(None, description="Filter documents with OCR enhancement"),
    limit: int = Query(50, ge=1, le=100, description="Result limit"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get all documents with filtering support including hybrid parsing filters"""
    try:
        documents = await processor.get_all_documents()
        
        # Status filtering
        if status:
            documents = [doc for doc in documents if doc.parsing_status == status]
        
        # OCR enhancement filtering
        if has_ocr_enhancement is not None:
            filtered_docs = []
            for doc in documents:
                if doc.parsing_status == 'completed' and doc.parsed_data:
                    has_ocr = any(hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced 
                                for elem in doc.parsed_data.elements)
                    if has_ocr_enhancement == has_ocr:
                        filtered_docs.append(doc)
                elif not has_ocr_enhancement:
                    # Include non-completed docs if we're looking for non-OCR enhanced
                    filtered_docs.append(doc)
            documents = filtered_docs
        
        # Limit results
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

@router.get("/documents/{doc_id}/elements/enhanced")
async def get_enhanced_document_elements(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """복합 요소 정보와 OCR 향상 정보를 포함한 향상된 요소 조회"""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="Parsed document not found.")
        
        elements = record.parsed_data.elements
        
        # 복합 요소, OCR 향상 요소, 일반 요소 구분
        composite_elements = [elem for elem in elements if elem.category == 'composite_table']
        ocr_enhanced_elements = [elem for elem in elements if hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced]
        regular_elements = [elem for elem in elements if elem.category != 'composite_table' and not (hasattr(elem, '_ocr_enhanced') and elem._ocr_enhanced)]
        
        return {
            "document_id": doc_id,
            "total_elements": len(elements),
            "composite_elements": {
                "count": len(composite_elements),
                "elements": [elem.model_dump() for elem in composite_elements]
            },
            "ocr_enhanced_elements": {
                "count": len(ocr_enhanced_elements),
                "elements": [elem.model_dump() for elem in ocr_enhanced_elements],
                "categories": list(set([elem.category for elem in ocr_enhanced_elements]))
            },
            "regular_elements": {
                "count": len(regular_elements), 
                "elements": [elem.model_dump() for elem in regular_elements]
            },
            "hybrid_parsing_applied": len(ocr_enhanced_elements) > 0,
            "enhancement_summary": {
                "composite_elements_created": len(composite_elements) > 0,
                "ocr_text_extraction_applied": len(ocr_enhanced_elements) > 0,
                "total_enhanced_elements": len(composite_elements) + len(ocr_enhanced_elements)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve enhanced elements: {str(e)}")

@router.get("/system/api-test")
async def test_upstage_api(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Test Upstage API connection and basic functionality"""
    try:
        # Test API connection
        test_result = await processor.upstage_client.test_api_connection()
        
        return {
            "upstage_api_test": test_result,
            "api_key_configured": bool(processor.upstage_client.api_key),
            "api_key_length": len(processor.upstage_client.api_key) if processor.upstage_client.api_key else 0,
            "api_url": processor.upstage_client.base_url
        }
    except Exception as e:
        return {
            "error": str(e),
            "api_key_configured": bool(processor.upstage_client.api_key),
            "api_key_length": len(processor.upstage_client.api_key) if processor.upstage_client.api_key else 0,
            "api_url": processor.upstage_client.base_url
        }

@router.get("/system/hybrid-capabilities")
async def get_hybrid_capabilities():
    """Get information about hybrid parsing capabilities"""
    return {
        "hybrid_parsing_available": True,
        "capabilities": {
            "ocr_text_extraction": {
                "description": "Extract text from images using Upstage OCR API",
                "supported_categories": ["table", "figure", "chart", "equation", "paragraph"],
                "languages": "Multi-language support"
            },
            "image_text_enhancement": {
                "description": "Enhance existing parsing with additional OCR extraction",
                "enhancement_criteria": [
                    "Elements with images but minimal text",
                    "Table elements without structured text",
                    "Chart/figure elements with insufficient descriptions"
                ]
            },
            "composite_element_creation": {
                "description": "Combine related image and text elements",
                "benefits": [
                    "Better document structure understanding",
                    "Improved content accessibility",
                    "Enhanced text searchability"
                ]
            }
        },
        "configuration": {
            "default_hybrid_parsing": True,
            "default_ocr_enhancement": True,
            "concurrent_ocr_limit": 3,
            "supported_image_formats": ["PNG", "JPEG", "BMP", "TIFF", "WEBP"]
        },
        "api_integration": {
            "document_parser": "https://api.upstage.ai/v1/document-digitization (model: document-parse)",
            "ocr_engine": "https://api.upstage.ai/v1/document-digitization (model: ocr)",
            "enhancement_strategy": "Hybrid approach with intelligent element analysis"
        }
    }