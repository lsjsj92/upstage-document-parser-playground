# project_path/backend/config.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Coordinate(BaseModel):
    """
    문서 내 특정 지점의 2D 좌표를 나타내는 모델

    Attributes:
        x: X축 좌표 (0.0~1.0 범위의 정규화된 값)
        y: Y축 좌표 (0.0~1.0 범위의 정규화된 값)
    """
    x: float
    y: float

class BoundingBox(BaseModel):
    """
    문서 요소의 바운딩 박스(경계 상자)를 나타내는 모델
    4개의 좌표점으로 구성된 사각형 영역을 정의합니다.

    Attributes:
        coordinates: 좌표 리스트 (좌상단, 우상단, 우하단, 좌하단 순서)
    """
    coordinates: List[Coordinate]

    @property
    def top_left(self) -> Coordinate:
        return self.coordinates[0]
    
    @property
    def bottom_right(self) -> Coordinate:
        return self.coordinates[2]
    
    @property
    def width(self) -> float:
        return abs(self.bottom_right.x - self.top_left.x)
    
    @property
    def height(self) -> float:
        return abs(self.bottom_right.y - self.top_left.y)

class ElementContent(BaseModel):
    """
    문서 요소의 콘텐츠를 다양한 형식으로 저장하는 모델

    Attributes:
        html: HTML 형식의 콘텐츠
        markdown: Markdown 형식의 콘텐츠
        text: 순수 텍스트 형식의 콘텐츠
    """
    html: str = ""
    markdown: str = ""
    text: str = ""

class DocumentElement(BaseModel):
    """
    문서를 구성하는 개별 요소(단락, 표, 이미지 등)를 나타내는 모델

    Attributes:
        id: 요소의 고유 ID
        category: 요소 유형 (heading1, paragraph, table, figure, chart 등)
        content: 요소의 콘텐츠 (HTML, Markdown, Text 형식)
        coordinates: 요소의 위치를 나타내는 좌표 리스트 (4개 좌표)
        page: 요소가 위치한 페이지 번호 (1부터 시작)
        base64_encoding: 이미지 데이터의 Base64 인코딩 문자열 (이미지 요소인 경우)
        image_mime_type: 이미지의 MIME 타입 (예: image/png, image/jpeg)
    """
    id: int
    category: str  # heading1, paragraph, table, figure, chart, etc.
    content: ElementContent
    coordinates: List[Coordinate]
    page: int
    base64_encoding: Optional[str] = None
    image_mime_type: Optional[str] = None

    @property
    def bounding_box(self) -> BoundingBox:
        return BoundingBox(coordinates=self.coordinates)

class DocumentContent(BaseModel):
    """
    문서 전체의 콘텐츠를 다양한 형식으로 저장하는 모델

    Attributes:
        html: 전체 문서의 HTML 형식 콘텐츠
        markdown: 전체 문서의 Markdown 형식 콘텐츠
        text: 전체 문서의 순수 텍스트 형식 콘텐츠
    """
    html: str = ""
    markdown: str = ""
    text: str = ""

class ParsedDocument(BaseModel):
    """
    Upstage API로부터 파싱된 문서의 전체 결과를 저장하는 모델

    Attributes:
        api: 사용된 API 이름 (예: upstage-document-parse)
        model: 사용된 모델 이름 (예: document-parse)
        content: 전체 문서의 통합 콘텐츠
        elements: 문서를 구성하는 개별 요소들의 리스트
        usage: API 사용량 정보 (토큰 수, 페이지 수 등)
    """
    api: str
    model: str
    content: DocumentContent
    elements: List[DocumentElement]
    usage: Dict[str, Any]

class DocumentRecord(BaseModel):
    """
    업로드된 문서의 메타데이터와 파싱 상태를 관리하는 모델

    Attributes:
        id: 문서의 고유 ID (UUID)
        filename: 저장된 파일명 (UUID + 확장자)
        original_filename: 원본 파일명
        file_path: 저장된 파일의 전체 경로
        file_size: 파일 크기 (바이트)
        content_type: 파일의 MIME 타입
        upload_time: 파일 업로드 시간
        parsing_status: 파싱 상태 (pending, processing, completed, failed)
        parsed_data: 파싱된 문서 데이터 (파싱 완료 시)
        error_message: 에러 메시지 (파싱 실패 시)
    """
    id: str
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    content_type: str
    upload_time: datetime
    parsing_status: str = "pending"  # pending, processing, completed, failed
    parsed_data: Optional[ParsedDocument] = None
    error_message: Optional[str] = None

    @property
    def is_parsed(self) -> bool:
        return self.parsing_status == "completed" and self.parsed_data is not None