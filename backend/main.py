# project_path/backend/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers.routes import router
from backend.config import config

# FastAPI app creation
app = FastAPI(
    title="Document Parser",
    description="Enhanced document parsing system using Upstage Document AI API",
    version="1.0.0"
)

# CORS middleware for Streamlit integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router, prefix="/api/v1", tags=["documents"])

@app.get("/")
async def root():
    return {
        "message": "Document Parser",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
        "features": [
            "enhanced_parsing",
            "image_extraction",
            "coordinate_preservation",
            "bounding_box_visualization"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "enhanced_mode": True,
        "features_enabled": [
            "force_ocr",
            "image_extraction",
            "coordinate_preservation",
            "element_based_splitting"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info"
    )