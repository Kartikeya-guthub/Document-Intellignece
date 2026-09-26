import os
import cv2
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models import Document, OcrElement, ExtractedField, ValidationFlag, TamperFlag
from app.preprocessing.pipeline import preprocess_document
from app.ocr.engine import run_ocr_and_layout
from app.llm.extractor import extract_with_llm
from app.validation.rules import persist_validation_flags, run_validation_rules
from app.confidence.engine import score_document_fields
from app.tamper.detector import run_tamper_checks, _resolve_path

logger = logging.getLogger(__name__)

def run_end_to_end_pipeline(document_id: str, db: Session) -> Dict[str, Any]:
    """
    Executes the entire document processing chain end-to-end:
    1. Preprocessing (deskew, contrast enhancement)
    2. OCR + Layout + Table Extraction (PaddleOCR GPU)
    3. LLM Schema Extraction + Source Citation (NVIDIA NIM)
    4. Business & Mathematical Validation Rules
    5. Phase 5 Confidence Scoring (Formula: 0.5*O + 0.3*S + 0.2*V with hard cap)
    6. Tamper Detection (Forensic Metadata + Error Level Analysis Heatmap)
    7. Overall Review Routing Status Update
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found.")

    logger.info(f"[Pipeline] Starting end-to-end run for document {document_id} ({doc.filename})")

    file_path = _resolve_path(doc.file_path)
    prep_path = _resolve_path(doc.preprocessed_path) if doc.preprocessed_path else None

    # Step 1: Preprocess if needed
    if not prep_path or not os.path.exists(prep_path):
        prep_dir = _resolve_path("storage/preprocessed")
        if not os.path.exists(prep_dir):
            prep_dir = os.path.join("backend", "storage", "preprocessed")
        os.makedirs(prep_dir, exist_ok=True)
        target_prep_path = os.path.join(prep_dir, f"{doc.id}_preprocessed.png")
        preprocess_document(file_path, target_prep_path)
        doc.preprocessed_path = target_prep_path
        prep_path = target_prep_path
        doc.status = "PREPROCESSED"
        db.commit()

    # Step 2: OCR + Layout if needed
    existing_elements = db.query(OcrElement).filter(OcrElement.document_id == doc.id).count()
    if existing_elements == 0 or doc.status in ["uploaded", "PREPROCESSED"]:
        img = cv2.imread(prep_path)
        if img is None:
            raise ValueError(f"Failed to read preprocessed image at {prep_path}")
        
        elements = run_ocr_and_layout(img, doc_id=str(doc.id))
        db.query(OcrElement).filter(OcrElement.document_id == doc.id).delete()
        
        db_elements = []
        for el in elements:
            db_el = OcrElement(
                document_id=doc.id,
                text=el["text"],
                bbox=el["bbox"],
                conf=el["confidence"],
                region_type=el["region_type"],
                row=el.get("table_row"),
                col=el.get("table_col"),
                page=el.get("page_number", 1),
                region_status=el.get("region_status", "OK"),
                heuristic_sourced=(el.get("region_type") == "table_cell"),
            )
            db_elements.append(db_el)
        db.bulk_save_objects(db_elements)
        doc.status = "OCR_DONE"
        db.commit()

    # Step 3: LLM Schema Extraction & Citation
    extract_res = extract_with_llm(str(doc.id), db=db)
    if "error" in extract_res:
        raise RuntimeError(f"LLM extraction step failed: {extract_res['error']}")

    # Refresh doc after LLM extraction
    db.refresh(doc)
    doc_type = doc.doc_type or "invoice"

    # Step 4: Validation Rules
    db_fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
    fields_dict = {f.field_name: f.extracted_value for f in db_fields if f.field_name != "line_item"}
    validation_flags = persist_validation_flags(str(doc.id), doc_type, fields_dict, db)
    validation_scores = run_validation_rules(doc_type, fields_dict)

    # Step 5: Confidence Scoring
    scored_fields = score_document_fields(str(doc.id), doc_type, validation_scores, db)

    # Step 6: Tamper Detection (Metadata + ELA)
    tamper_report = run_tamper_checks(str(doc.id), db)

    # Step 7: Final Status Determination
    needs_review = any(f["review_status"] == "needs_review" for f in scored_fields)
    has_tamper_risk = tamper_report.get("overall_tamper_risk") in ["HIGH", "MEDIUM"]
    has_failed_validation = any(not vf["passed"] for vf in validation_flags)

    if needs_review or has_tamper_risk or has_failed_validation:
        doc.status = "NEEDS_REVIEW"
    else:
        doc.status = "APPROVED"
    db.commit()

    return generate_full_report(str(doc.id), db)


def generate_full_report(document_id: str, db: Session) -> Dict[str, Any]:
    """Generates the unified full-report JSON for a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found.")

    fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).all()
    v_flags = db.query(ValidationFlag).filter(ValidationFlag.document_id == doc.id).all()
    t_flags = db.query(TamperFlag).filter(TamperFlag.document_id == doc.id).all()
    total_elements = db.query(OcrElement).filter(OcrElement.document_id == doc.id).count()

    scalar_fields = {}
    line_items = []
    could_not_extract = []

    for f in fields:
        if f.field_name == "line_item":
            item_data = {}
            if f.extracted_value:
                try:
                    item_data = json.loads(f.extracted_value)
                except Exception:
                    item_data = {"raw": f.extracted_value}
            line_items.append({
                "group_id": f.line_item_group_id,
                "data": item_data,
                "confidence": f.final_confidence,
                "ocr_confidence": f.ocr_confidence,
                "string_similarity": f.string_similarity,
                "validation_pass": f.validation_pass,
                "review_status": f.review_status,
                "source_element_ids": f.source_element_ids or []
            })
        else:
            is_extracted = f.extracted_value is not None and f.extracted_value != "None"
            if not is_extracted:
                could_not_extract.append(f.field_name)

            scalar_fields[f.field_name] = {
                "value": f.extracted_value if is_extracted else None,
                "confidence": f.final_confidence,
                "ocr_confidence": f.ocr_confidence,
                "string_similarity": f.string_similarity,
                "validation_pass": f.validation_pass,
                "review_status": f.review_status,
                "source_element_ids": f.source_element_ids or [],
                "raw_ocr_text": f.raw_ocr_text
            }

    tamper_summary = {
        "overall_risk": "LOW",
        "checks": []
    }
    for tf in t_flags:
        heatmap_url = f"/storage/tamper/{os.path.basename(tf.heatmap_path)}" if tf.heatmap_path else None
        tamper_summary["checks"].append({
            "check_type": tf.check_type,
            "result": tf.result,
            "risk_level": tf.risk_level,
            "heatmap_path": tf.heatmap_path,
            "heatmap_url": heatmap_url,
            "details": tf.details
        })
        if tf.risk_level == "HIGH":
            tamper_summary["overall_risk"] = "HIGH"
        elif tf.risk_level == "MEDIUM" and tamper_summary["overall_risk"] != "HIGH":
            tamper_summary["overall_risk"] = "MEDIUM"

    validation_summary = [
        {
            "rule_name": vf.rule_name,
            "field_name": vf.field_name,
            "passed": vf.passed,
            "details": vf.details
        }
        for vf in v_flags
    ]

    # Duplication check
    duplication_info = {
        "is_duplicate": doc.doc_metadata.get("is_duplicate", False) if doc.doc_metadata else False,
        "duplicate_of": doc.doc_metadata.get("duplicate_of", None) if doc.doc_metadata else None,
        "duplicate_type": doc.doc_metadata.get("duplicate_type", None) if doc.doc_metadata else None,
        "sha256": doc.doc_metadata.get("sha256", None) if doc.doc_metadata else None,
        "semantic_duplicate": False,
        "semantic_reason": None
    }
    
    # Check semantic duplicate on invoice_number
    if doc.doc_type == "invoice" and "invoice_number" in scalar_fields:
        inv_val = scalar_fields["invoice_number"].get("value")
        if inv_val:
            prior_doc_field = db.query(ExtractedField).filter(
                ExtractedField.document_id != doc.id,
                ExtractedField.field_name == "invoice_number",
                ExtractedField.extracted_value == inv_val
            ).first()
            if prior_doc_field:
                duplication_info["semantic_duplicate"] = True
                duplication_info["semantic_reason"] = f"Invoice number '{inv_val}' matches prior document {prior_doc_field.document_id}"
                duplication_info["semantic_duplicate_of"] = str(prior_doc_field.document_id)

    return {
        "document_id": str(doc.id),
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "preprocessed_image_url": f"/storage/preprocessed/{os.path.basename(doc.preprocessed_path)}" if doc.preprocessed_path else None,
        "total_ocr_elements": total_elements,
        "duplication_status": duplication_info,
        "extracted_fields": scalar_fields,
        "line_items": line_items,
        "could_not_extract": could_not_extract,
        "validation_flags": validation_summary,
        "tamper_detection": tamper_summary
    }
