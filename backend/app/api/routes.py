import hashlib
import cv2
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import Document, OcrElement, ExtractedField, TamperFlag, ValidationFlag
from app.preprocessing.pipeline import convert_pdf_to_image, preprocess_document
from app.ocr.engine import run_ocr_and_layout
from app.llm.extractor import extract_with_llm
from app.pipeline import run_end_to_end_pipeline, generate_full_report

router = APIRouter(prefix="/api/v1", tags=["Documents"])

STORAGE_DIR = "storage"
RAW_DIR = os.path.join(STORAGE_DIR, "raw")
PREP_DIR = os.path.join(STORAGE_DIR, "preprocessed")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PREP_DIR, exist_ok=True)


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...), 
    run_full_pipeline: bool = True,
    db: Session = Depends(get_db)
):
    """
    End-to-End Document Upload:
    1. Accepts PDF/Image
    2. Runs duplicate detection (SHA-256)
    3. Preprocesses and deskews image
    4. If run_full_pipeline=True (default), automatically runs:
       - GPU OCR & Table layout extraction
       - LLM schema extraction & source citation
       - Arithmetic & temporal validation
       - Multi-factor confidence scoring
       - Dual forensic tamper checks (PDF metadata + ELA heatmap)
    5. Returns full report immediately in one single response.
    """
    ext = file.filename.split(".")[-1].lower()
    if ext not in ["pdf", "png", "jpg", "jpeg", "webp"]:
        raise HTTPException(status_code=400, detail="Only PDF or image files (pdf, png, jpg, jpeg, webp) are supported.")

    doc_id = uuid.uuid4()

    # Read content to compute SHA-256 for exact byte-level duplicate detection
    content = await file.read()
    file_sha256 = hashlib.sha256(content).hexdigest()

    # Check for existing document with identical byte hash
    all_docs = db.query(Document).all()
    duplicate_doc = None
    for d in all_docs:
        if d.doc_metadata and d.doc_metadata.get("sha256") == file_sha256:
            duplicate_doc = d
            break

    is_duplicate = duplicate_doc is not None
    duplicate_of = str(duplicate_doc.id) if duplicate_doc else None

    # Save raw file
    raw_path = os.path.join(RAW_DIR, f"{doc_id}.{ext}")
    with open(raw_path, "wb") as buffer:
        buffer.write(content)

    working_image_path = raw_path

    # If PDF, convert to image
    if ext == "pdf":
        img_path = os.path.join(RAW_DIR, f"{doc_id}_converted.png")
        working_image_path = convert_pdf_to_image(raw_path, img_path)

    # Run preprocessing pipeline
    prep_path = os.path.join(PREP_DIR, f"{doc_id}_preprocessed.png")
    preprocess_document(working_image_path, prep_path)

    # Persist document record
    new_doc = Document(
        id=doc_id,
        filename=file.filename,
        file_path=raw_path,
        preprocessed_path=prep_path,
        status="PREPROCESSED",
        doc_metadata={
            "sha256": file_sha256,
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "duplicate_type": "byte_exact" if is_duplicate else None
        }
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)

    if run_full_pipeline:
        try:
            full_report = run_end_to_end_pipeline(str(new_doc.id), db=db)
            full_report["message"] = "Upload and full pipeline execution successful."
            if is_duplicate:
                full_report["message"] += f" (Duplicate of document {duplicate_of})"
            return full_report
        except Exception as e:
            return {
                "document_id": str(new_doc.id),
                "status": new_doc.status,
                "is_duplicate": is_duplicate,
                "duplicate_of": duplicate_of,
                "pipeline_error": str(e),
                "message": f"Upload succeeded, but automatic pipeline encountered error: {str(e)}"
            }

    return {
        "document_id": str(new_doc.id),
        "status": new_doc.status,
        "is_duplicate": is_duplicate,
        "duplicate_of": duplicate_of,
        "sha256": file_sha256,
        "message": "Duplicate document detected (exact byte match)." if is_duplicate else "Upload and preprocessing successful.",
    }


@router.post("/documents/{doc_id}/process")
def process_document(doc_id: str, db: Session = Depends(get_db)):
    """
    Phase 3: OCR + Layout + Table Extraction
    1. Load preprocessed image for doc_id
    2. Run PaddleOCR text detection + recognition
    3. Run PPStructureV3 layout detection
    4. Apply OCR-failure gate (conf < 0.3 -> UNPROCESSABLE)
    5. Persist all elements to ocr_elements table with heuristic_sourced flag
    6. Update document status to OCR_DONE
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    if not doc.preprocessed_path or not os.path.exists(doc.preprocessed_path):
        raise HTTPException(
            status_code=400,
            detail="Preprocessed image not found. Run /upload first.",
        )
    if doc.status == "OCR_DONE":
        raise HTTPException(
            status_code=400,
            detail="OCR already completed for this document. Reprocessing not supported yet.",
        )

    # Run OCR + layout + table extraction
    img = cv2.imread(doc.preprocessed_path)
    if img is None:
        raise HTTPException(status_code=500, detail="Failed to load preprocessed image.")
    elements = run_ocr_and_layout(img, doc_id=str(doc.id))

    # Persist to ocr_elements table
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

    # Update document status
    doc.status = "OCR_DONE"
    db.commit()

    total = len(elements)
    unprocessable = sum(1 for e in elements if e["region_status"] == "UNPROCESSABLE")
    region_types = {}
    for e in elements:
        region_types[e["region_type"]] = region_types.get(e["region_type"], 0) + 1

    return {
        "document_id": doc_id,
        "status": "OCR_DONE",
        "summary": {
            "total_elements": total,
            "unprocessable_count": unprocessable,
            "by_region_type": region_types,
        },
        "message": "OCR extraction complete. LLM structuring available via /extract.",
    }


@router.post("/documents/{doc_id}/extract")
def extract_document_fields(doc_id: str, db: Session = Depends(get_db)):
    """Phase 4: LLM Schema Mapping + Source Citation + Validation & Confidence Scoring."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    res = extract_with_llm(doc_id, db=db)
    if "error" in res:
        raise HTTPException(status_code=500, detail=res["error"])
    
    # Run validation and confidence scoring automatically
    try:
        from app.validation.rules import validate_document
        from app.confidence.engine import score_document_fields
        validate_document(doc_id, db)
        score_document_fields(doc_id, db)
    except Exception as e:
        print(f"Validation/confidence error: {e}")

    return res


@router.post("/documents/{doc_id}/pipeline")
def trigger_full_pipeline(doc_id: str, db: Session = Depends(get_db)):
    """Runs the complete end-to-end processing pipeline for a document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    try:
        report = run_end_to_end_pipeline(doc_id, db=db)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@router.get("/documents/{doc_id}/full-report")
def get_full_report(doc_id: str, db: Session = Depends(get_db)):
    """
    Returns full end-to-end report:
    - Extracted fields with confidence scores and review flags
    - Line items with groups
    - Validation flags
    - Tamper detection analysis (metadata + ELA)
    - Could not extract fields
    """
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    try:
        report = generate_full_report(doc_id, db=db)
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/documents/{doc_id}/ocr")
async def get_ocr_elements(doc_id: str, db: Session = Depends(get_db)):
    """Return all OCR elements for a document."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    elements = db.query(OcrElement).filter(OcrElement.document_id == doc_id).all()
    return {
        "document_id": doc_id,
        "status": doc.status,
        "elements": [
            {
                "id":                 str(el.id),
                "text":               el.text,
                "bbox":               el.bbox,
                "conf":               el.conf,
                "region_type":        el.region_type,
                "row":                el.row,
                "col":                el.col,
                "page":               el.page,
                "region_status":      el.region_status,
                "heuristic_sourced":  el.heuristic_sourced,
            }
            for el in elements
        ],
    }


@router.get("/documents/{doc_id}/fields")
def get_extracted_fields(doc_id: str, db: Session = Depends(get_db)):
    """Return all extracted fields for a document, including source citations."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc_id).all()
    return {
        "document_id": doc_id,
        "status": doc.status,
        "doc_type": doc.doc_type,
        "fields": [
            {
                "field_name":         f.field_name,
                "extracted_value":    f.extracted_value,
                "final_confidence":   f.final_confidence,
                "ocr_confidence":     f.ocr_confidence,
                "string_similarity":  f.string_similarity,
                "validation_pass":    f.validation_pass,
                "review_status":      f.review_status,
                "source_element_ids": f.source_element_ids,
                "line_item_group_id": f.line_item_group_id,
                "extracted_at":       f.extracted_at.isoformat() if f.extracted_at else None,
            }
            for f in fields
        ]
    }


@router.post("/documents/{doc_id}/tamper")
def run_tamper_check_endpoint(doc_id: str, db: Session = Depends(get_db)):
    """Run forensic tamper detection (PDF Metadata + Error Level Analysis) on a document."""
    from app.tamper.detector import run_tamper_checks
    try:
        results = run_tamper_checks(doc_id, db)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_id}/tamper")
def get_tamper_flags_endpoint(doc_id: str, db: Session = Depends(get_db)):
    """Retrieve stored tamper detection flags and ELA heatmap link for a document."""
    flags = db.query(TamperFlag).filter(TamperFlag.document_id == doc_id).all()
    if not flags:
        return {"document_id": doc_id, "tamper_checks": [], "message": "No tamper checks run yet. Call POST /documents/{doc_id}/tamper."}
    
    return {
        "document_id": doc_id,
        "tamper_checks": [
            {
                "check_type": tf.check_type,
                "result": tf.result,
                "risk_level": tf.risk_level,
                "heatmap_url": f"/storage/tamper/{os.path.basename(tf.heatmap_path)}" if tf.heatmap_path else None,
                "details": tf.details
            }
            for tf in flags
        ]
    }
