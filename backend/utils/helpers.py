# project_path/backend/utils/helpers.py

import base64
from typing import Optional


def get_image_mime_type_from_base64(base64_string: str) -> Optional[str]:
    """
    Base64 인코딩된 이미지 문자열로부터 MIME 타입을 판별합니다.

    매직 넘버(파일 시그니처)를 분석하여 실제 이미지 형식을 확인합니다.

    Args:
        base64_string: Base64로 인코딩된 이미지 데이터 문자열

    Returns:
        Optional[str]: 이미지 MIME 타입 (image/png, image/jpeg 등)
                      판별 실패 시 None 반환
    """
    try:
        decoded_data = base64.b64decode(base64_string[:20])

        if decoded_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        elif decoded_data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif decoded_data.startswith(b'GIF87a') or decoded_data.startswith(b'GIF89a'):
            return 'image/gif'
        elif decoded_data.startswith(b'BM'):
            return 'image/bmp'
        elif decoded_data.startswith(b'RIFF') and decoded_data[8:12] == b'WEBP':
            return 'image/webp'
        else:
            # If unknown, default to jpeg as a common fallback
            return 'image/jpeg'
    except (base64.binascii.Error, IndexError):
        # 디코딩 실패 시(base64가 아닌 것)
        return None

