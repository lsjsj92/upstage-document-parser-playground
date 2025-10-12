# project_path/backend/utils/helpers.py
"""
유틸리티 헬퍼 함수들
Windows/Linux 호환성을 위한 공통 함수들을 제공합니다.
"""

import re, os
import socket
import hashlib
import platform
from pathlib import Path
from typing import Union, Optional
import mimetypes
import base64
from typing import Optional

def get_image_mime_type_from_base64(base64_string: str) -> Optional[str]:
    """
    Decodes the first few bytes of a Base64 string to determine the image MIME type.
    Base64 문자열의 시작 부분을 디코딩하여 실제 이미지 MIME 타입을 판별합니다.
    """
    try:
        # Decode the base64 string to get the image header bytes
        decoded_data = base64.b64decode(base64_string[:20]) # First 20 chars are enough

        # Check for common image file format headers (Magic Numbers)
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
        # If decoding fails, it's not a valid base64 string for an image
        return None

