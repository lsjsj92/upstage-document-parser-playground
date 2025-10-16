# project_path/frontend/utils/config.py

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Backend API Connection (프론트엔드에서 백엔드 API 호출용)
    HOST: str = "localhost"
    PORT: int = 8000
    
    @property
    def API_BASE_URL(self) -> str:
        """백엔드 API의 기본 URL을 반환"""
        return f"http://{self.HOST}:{self.PORT}/api/v1"

    # Streamlit Configuration (프론트엔드 서버용)
    STREAMLIT_PORT: int = 8501

    # UI Configuration (프론트엔드 UI 설정용)
    MAX_FILE_SIZE_DISPLAY: str = "50MB"  # UI에 표시할 파일 크기 제한
    ALLOWED_EXTENSIONS: list = ["pdf", "docx", "pptx", "jpg", "jpeg", "png"]

    # Debug Mode (프론트엔드 디버깅용)
    DEBUG: bool = True

# 인스턴스 생성
config = Config()