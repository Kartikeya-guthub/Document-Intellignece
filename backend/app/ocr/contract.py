from pydantic import BaseModel, Field
from typing import Optional, Literal, List

class OCRRegionContract(BaseModel):
    """
    Locked data contract: every OCR text region must carry this shape downstream to the LLM.
    """
    text: str = Field(..., description="Raw text recognized by OCR")
    bbox: List[float] = Field(..., min_length=4, max_length=4, description="Bounding box [x, y, w, h]")
    conf: float = Field(..., ge=0.0, le=1.0, description="OCR word/region confidence score (0 to 1)")
    region_type: Literal["table_cell", "paragraph", "title", "figure"] = Field(
        ..., description="Detected layout block classification"
    )
    row: Optional[int] = Field(None, description="Row index if table_cell, else null")
    col: Optional[int] = Field(None, description="Column index if table_cell, else null")
    page: int = Field(1, ge=1, description="1-indexed page number")
