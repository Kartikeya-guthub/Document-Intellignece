import Levenshtein
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.db.models import ExtractedField, OcrElement

def calculate_field_confidence(o: float, s: float, v: int) -> float:
    """
    Locked Confidence Formula:
        confidence = 0.5*O + 0.3*S + 0.2*V
        
    Inputs (0.0 to 1.0):
        O = OCR confidence of cited source span(s).
        S = String-similarity (normalized Levenshtein) between LLM value and raw OCR text.
        V = Binary validation pass (1 if satisfied or not applicable, 0 if failed).
        
    HARD CAP:
        If V = 0 due to a failed validation check, confidence is capped at 0.5 regardless of O and S.
        
    Routing Threshold:
        confidence < 0.7 routes the field to human review.
    """
    base_confidence = (0.5 * o) + (0.3 * s) + (0.2 * float(v))
    if v == 0:
        return min(base_confidence, 0.5)
    return round(base_confidence, 4)

def score_document_fields(document_id: str, doc_type: str, validation_scores: Dict[str, int], db: Session) -> List[Dict[str, Any]]:
    """
    Computes and persists Phase 5 confidence scores for all ExtractedField rows for a document.
    """
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == document_id).all()
    all_elements = db.query(OcrElement).filter(OcrElement.document_id == document_id).all()
    elem_map = {str(el.id): el for el in all_elements}

    scored_summary = []
    for f in fields:
        # 1. Calculate O (OCR confidence)
        cites = f.source_element_ids or []
        cited_elems = [elem_map[cid] for cid in cites if cid in elem_map]
        
        if cited_elems:
            # Average OCR confidence across cited tokens
            avg_o = sum(float(e.conf) for e in cited_elems) / len(cited_elems)
            raw_text = " ".join(e.text for e in cited_elems).strip()
            
            # Heuristic penalty: if any cited element is heuristic_sourced, cap ceiling at 0.85
            is_heuristic = any(getattr(e, "heuristic_sourced", False) for e in cited_elems)
            if is_heuristic:
                avg_o = min(avg_o, 0.85)
        else:
            avg_o = 0.0
            raw_text = ""

        # 2. Calculate S (String Similarity)
        val_str = str(f.extracted_value or "").strip()
        if not val_str:
            s_score = 0.0
        elif not raw_text:
            s_score = 0.0
        else:
            s_score = Levenshtein.ratio(val_str.lower(), raw_text.lower())

        # 3. Get V (Validation Pass)
        v_score = validation_scores.get(f.field_name, 1)

        # 4. Compute Final Confidence
        final_conf = calculate_field_confidence(avg_o, s_score, v_score)
        
        # 5. Routing status
        review_status = "auto_accepted" if final_conf >= 0.7 else "needs_review"

        # Update ExtractedField row
        f.ocr_confidence = round(avg_o, 4)
        f.string_similarity = round(s_score, 4)
        f.validation_pass = v_score
        f.final_confidence = final_conf
        f.raw_ocr_text = raw_text
        f.review_status = review_status

        scored_summary.append({
            "field_name": f.field_name,
            "extracted_value": f.extracted_value,
            "ocr_confidence": round(avg_o, 4),
            "string_similarity": round(s_score, 4),
            "validation_pass": v_score,
            "final_confidence": final_conf,
            "review_status": review_status,
            "cites_count": len(cites)
        })

    db.commit()
    return scored_summary
