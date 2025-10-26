# project_path/frontend/components/file_uploader.py

import requests
from typing import Tuple, Any

class FileUploader:
    """
    파일 업로드를 담당하는 Streamlit 컴포넌트 클래스

    백엔드 API 서버로 파일을 전송하고 응답을 처리합니다.
    """

    def __init__(self, api_base_url: str):
        """
        FileUploader를 초기화합니다.

        Args:
            api_base_url: 백엔드 API 기본 URL
        """
        self.api_base_url = api_base_url

    def upload_file(self, uploaded_file) -> Tuple[bool, Any]:
        """
        파일을 백엔드 API 서버로 업로드합니다.

        Args:
            uploaded_file: Streamlit UploadedFile 객체

        Returns:
            Tuple[bool, Any]: (성공 여부, 결과 데이터 또는 에러 메시지)
                             성공 시 (True, 문서 레코드 JSON)
                             실패 시 (False, 에러 메시지 문자열)
        """
        try:
            files = {
                'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
            }
            
            response = requests.post(
                f"{self.api_base_url}/upload",
                files=files,
                timeout=300  # 5 minute timeout for large files
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', error_detail)
                except:
                    error_detail = response.text
                return False, f"Upload failed ({response.status_code}): {error_detail}"
                
        except requests.exceptions.Timeout:
            return False, "Upload timed out. Please try with a smaller file."
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to API server. Please check if the server is running."
        except Exception as e:
            return False, f"Upload error: {str(e)}"