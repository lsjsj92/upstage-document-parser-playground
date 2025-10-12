# project_path/backend/config.py

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

    # API Configuration
    UPSTAGE_API_KEY: str = ""
    UPSTAGE_API_URL: str = "https://api.upstage.ai/v1/document-digitization"
    

    # File Upload Settings
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB in bytes

    # Directory Structure
    BASE_DIR: Path = Path(__file__).parent.parent  # project_path 디렉토리
    STORAGE_DIR: Path = BASE_DIR / "storage"        # project_path/storage
    UPLOADS_DIR: Path = STORAGE_DIR / "uploads"     # project_path/storage/uploads
    PARSED_DIR: Path = STORAGE_DIR / "parsed"       # project_path/storage/parsed

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    @classmethod
    def create_directories(cls):
        """Create necessary directories with error handling"""
        cfg = cls()
        
        directories = [cfg.STORAGE_DIR, cfg.UPLOADS_DIR, cfg.PARSED_DIR]
        
        print(f"[Config] Base directory: {cfg.BASE_DIR}")
        print(f"[Config] Creating storage directories")
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                print(f"[Config] ✓ Directory created/verified: {directory}")
                
                # 쓰기 권한 확인
                test_file = directory / ".test_write"
                try:
                    test_file.touch()
                    test_file.unlink()
                    print(f"[Config] ✓ Write permission confirmed: {directory}")
                except Exception as e:
                    print(f"[Config] ⚠ Write permission issue: {directory} - {e}")
                    
            except Exception as e:
                print(f"[Config] ✗ Failed to create directory: {directory} - {e}")
                raise Exception(f"Critical: Cannot create storage directory {directory}: {e}")

    def ensure_directories_exist(self):
        """Runtime에서 디렉토리 존재 확인 (instance method)"""
        directories = [self.STORAGE_DIR, self.UPLOADS_DIR, self.PARSED_DIR]
        
        for directory in directories:
            if not directory.exists():
                print(f"[Config] Runtime directory creation: {directory}")
                directory.mkdir(parents=True, exist_ok=True)

# Global configuration instance
config = Config()

# 초기 디렉토리 생성
try:
    Config.create_directories()
except Exception as e:
    print(f"[Config] CRITICAL ERROR: {e}")
    print(f"[Config] Please check directory permissions and disk space")

if not config.UPSTAGE_API_KEY:
    print("Warning: UPSTAGE_API_KEY not found. Please set it in .env or environment variables.")