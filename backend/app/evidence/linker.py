from typing import Dict, Any
from app.ocr.contract import OCRRegionContract

def link_evidence_to_field(
    field_name: str,
    source_span_id: int,
    ocr_regions: list[OCRRegionContract]
) -> Dict[str, Any]:
    """
    STUB: Evidence linking (field -> bbox -> page) for reviewer UI overlay (Phase 6+).
    """
    # NO EVIDENCE MAPPING IN PHASE 1
    raise NotImplementedError("Evidence linking will be implemented in Phase 6.")
