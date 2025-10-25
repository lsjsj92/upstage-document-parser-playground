# project_path/frontend/utils/config.py

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Config(BaseSettings):
    """
    Streamlit 프론트엔드의 설정을 관리하는 클래스

    백엔드 API 연결 정보, UI 설정, 디버그 모드 등을 관리합니다.
    """
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
        """
        백엔드 API의 기본 URL을 반환합니다.

        Returns:
            str: 백엔드 API URL (예: http://localhost:8000/api/v1)
        """
        return f"http://{self.HOST}:{self.PORT}/api/v1"

# 인스턴스 생성
config = Config()