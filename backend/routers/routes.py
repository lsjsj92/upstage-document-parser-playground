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
    Upload file for parsing. OCR and text extraction are handled automatically by Upstage API.
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
    """Get images extracted from document"""
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
    """Reprocess document - Upstage API automatically handles OCR"""
    try:
        options = {"extract_images": True}
        
        success = await processor.reprocess_document_with_enhanced_settings(doc_id, options)
        if not success:
            raise HTTPException(status_code=404, detail="Document not found or reprocessing failed.")
        
        return {
            "message": "Document reprocessing started.", 
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
    """Get document elements with filtering options"""
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
        
        # Add ocr_enhanced flag to response
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
    """Get analysis summary for document - simplified version"""
    try:
        stats = await processor.get_parsing_statistics(doc_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Document statistics not found.")
        
        total_elements = stats.get('total_elements', 0)
        ocr_elements = stats.get('ocr_enhanced_elements', 0)
        image_elements = stats.get('elements_with_images', 0)

        return {
            "document_id": doc_id,
            "ocr_enhanced_elements": {
                "count": ocr_elements,
                "percentage": (ocr_elements / total_elements * 100) if total_elements > 0 else 0
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
        raise HTTPException(status_code=500, detail=f"Failed to retrieve analysis: {str(e)}")

@router.get("/documents/{doc_id}/markdown", response_class=PlainTextResponse)
async def get_document_markdown(
    doc_id: str,
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get full document content as Markdown"""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="Parsed document not found.")
        
        markdown_content = record.parsed_data.content.markdown
        if not markdown_content:
            return "No Markdown content available for this document."

        return PlainTextResponse(content=markdown_content, media_type="text/markdown")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve Markdown: {str(e)}")

@router.get("/queue/status")
async def get_queue_status(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get processing queue status"""
    try:
        status = await processor.get_processing_queue_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve queue status: {str(e)}")

@router.get("/health")
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "features": [
            "document_parsing",
            "ocr_text_extraction",
            "image_extraction", 
            "coordinate_preservation",
            "table_recognition",
            "chart_recognition"
        ]
    }

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

@router.get("/documents/{doc_id}/preview")
async def get_document_preview(
    doc_id: str,
    page: int = Query(1, description="Page number to preview"),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Get document preview for specific page"""
    try:
        record = await processor.get_document(doc_id)
        if not record or not record.is_parsed:
            raise HTTPException(status_code=404, detail="Parsed document not found.")
        
        page_elements = [elem for elem in record.parsed_data.elements if elem.page == page]
        
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
            "image_count": len(image_elements)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve preview: {str(e)}")

@router.post("/upload/batch", response_model=List[DocumentRecord])
async def upload_files_batch(
    files: List[UploadFile] = File(...),
    processor: FileProcessor = Depends(get_file_processor)
):
    """Batch file upload"""
    try:
        file_list = []
        for file in files:
            file_content = await file.read()
            
            is_valid, error_message = processor.validate_file(file.filename, len(file_content))
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"{file.filename}: {error_message}")
            
            file_list.append({
                'content': file_content,
                'filename': file.filename,
                'content_type': file.content_type or "application/octet-stream"
            })
        
        options = {"extract_images": True}
        
        records = await processor.process_file_batch(file_list, options)
        return records
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch upload failed: {str(e)}")

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

@router.get("/system/api-test")
async def test_upstage_api(
    processor: FileProcessor = Depends(get_file_processor)
):
    """Test Upstage API connection"""
    try:
        test_result = await processor.upstage_client.test_api_connection()
        
        return {
            "upstage_api_test": test_result,
            "api_key_configured": bool(processor.upstage_client.api_key),
            "api_url": processor.upstage_client.base_url
        }
    except Exception as e:
        return {
            "error": str(e),
            "api_key_configured": bool(processor.upstage_client.api_key),
            "api_url": processor.upstage_client.base_url
        }