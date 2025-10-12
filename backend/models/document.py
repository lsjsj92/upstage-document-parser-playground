# project_path/backend/config.py

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Coordinate(BaseModel):
    x: float
    y: float

class BoundingBox(BaseModel):
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
    html: str = ""
    markdown: str = ""
    text: str = ""

class DocumentElement(BaseModel):
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
    html: str = ""
    markdown: str = ""
    text: str = ""

class ParsedDocument(BaseModel):
    api: str
    model: str
    content: DocumentContent
    elements: List[DocumentElement]
    usage: Dict[str, Any]
    
class DocumentRecord(BaseModel):
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
    
    @property
    def total_pages(self) -> int:
        if not self.parsed_data:
            return 0
        return max([elem.page for elem in self.parsed_data.elements], default=0)
    
    def get_elements_by_page(self, page: int) -> List[DocumentElement]:
        if not self.parsed_data:
            return []
        return [elem for elem in self.parsed_data.elements if elem.page == page]
    
    def get_elements_by_category(self, category: str) -> List[DocumentElement]:
        if not self.parsed_data:
            return []
        return [elem for elem in self.parsed_data.elements if elem.category == category]