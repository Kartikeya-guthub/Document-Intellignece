import os
import cv2
import uuid
import logging
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models import Document, TamperFlag

logger = logging.getLogger(__name__)

def _resolve_path(path: str) -> str:
    if not path:
        return ""
    if os.path.exists(path):
        return path
    backend_path = os.path.join("backend", path)
    if os.path.exists(backend_path):
        return backend_path
    if path.startswith("backend" + os.sep) or path.startswith("backend/"):
        stripped = path[len("backend/"):].lstrip("\\/")
        if os.path.exists(stripped):
            return stripped
    return path

def _get_tamper_dir() -> str:
    base = "storage/tamper" if os.path.exists("storage") else "backend/storage/tamper"
    os.makedirs(base, exist_ok=True)
    return base

KNOWN_EDITING_TOOLS = [
    "photoshop", "acrobat pro", "gimp", "illustrator", "canva", "indesign", 
    "pdfescape", "sejda", "foxit phantom", "nitro pro", "coreldraw"
]

def _parse_pdf_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    cleaned = date_str.replace("D:", "").replace("'", "")
    digits = "".join(filter(str.isdigit, cleaned))
    if len(digits) >= 14:
        try:
            return datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
        except ValueError:
            pass
    if len(digits) >= 8:
        try:
            return datetime.strptime(digits[:8], "%Y%m%d")
        except ValueError:
            pass
    return None

def metadata_tamper_check(document_id: str, db: Session) -> Dict[str, Any]:
    """
    Forensic PDF Metadata Check:
    - Inspects creation date vs modification date
    - Inspects producer/creator software strings
    - If input is an image (JPG/PNG), returns NOT_APPLICABLE (does not fabricate a result)
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    file_path = _resolve_path(doc.file_path)
    ext = os.path.splitext(file_path)[1].lower().replace(".", "")

    if ext != "pdf":
        details = {
            "file_type": ext,
            "reason": "no PDF metadata available for image input (EXIF only, no PDF producer structure)",
            "producer": None,
            "creator": None,
            "creation_date": None,
            "modification_date": None
        }
        tamper_flag = TamperFlag(
            id=uuid.uuid4(),
            document_id=doc.id,
            check_type="metadata",
            result="NOT_APPLICABLE",
            risk_level="N/A",
            details=details,
            heatmap_path=None,
            created_at=datetime.utcnow()
        )
        db.add(tamper_flag)
        db.commit()
        return {
            "check_type": "metadata",
            "result": "NOT_APPLICABLE",
            "risk_level": "N/A",
            "details": details
        }

    try:
        import fitz
        pdf_doc = fitz.open(file_path)
        meta = pdf_doc.metadata or {}
        pdf_doc.close()

        creation_raw = meta.get("creationDate")
        mod_raw = meta.get("modDate")
        producer = (meta.get("producer") or "").strip()
        creator = (meta.get("creator") or "").strip()

        creation_dt = _parse_pdf_date(creation_raw)
        mod_dt = _parse_pdf_date(mod_raw)

        suspicious_date = False
        date_diff_seconds = 0
        if creation_dt and mod_dt:
            diff = (mod_dt - creation_dt).total_seconds()
            date_diff_seconds = diff
            if diff > 5:
                suspicious_date = True

        tool_matched = None
        for tool in KNOWN_EDITING_TOOLS:
            if tool in producer.lower() or tool in creator.lower():
                tool_matched = tool
                break

        suspicious_tool = tool_matched is not None

        if suspicious_date and suspicious_tool:
            result = "SUSPICIOUS"
            risk_level = "HIGH"
        elif suspicious_date or suspicious_tool:
            result = "SUSPICIOUS"
            risk_level = "MEDIUM"
        else:
            result = "CLEAN"
            risk_level = "LOW"

        details = {
            "producer": producer,
            "creator": creator,
            "creation_date": creation_dt.isoformat() if creation_dt else creation_raw,
            "modification_date": mod_dt.isoformat() if mod_dt else mod_raw,
            "date_diff_seconds": date_diff_seconds,
            "suspicious_modification_date": suspicious_date,
            "suspicious_editing_tool": suspicious_tool,
            "editing_tool_matched": tool_matched,
            "disclaimer": "Metadata check is a forensic heuristic, not absolute proof."
        }

        tamper_flag = TamperFlag(
            id=uuid.uuid4(),
            document_id=doc.id,
            check_type="metadata",
            result=result,
            risk_level=risk_level,
            details=details,
            heatmap_path=None,
            created_at=datetime.utcnow()
        )
        db.add(tamper_flag)
        db.commit()

        return {
            "check_type": "metadata",
            "result": result,
            "risk_level": risk_level,
            "details": details
        }

    except Exception as e:
        logger.error(f"Error during metadata check for document {doc.id}: {e}")
        details = {"error": str(e)}
        tamper_flag = TamperFlag(
            id=uuid.uuid4(),
            document_id=doc.id,
            check_type="metadata",
            result="NOT_APPLICABLE",
            risk_level="N/A",
            details=details,
            heatmap_path=None,
            created_at=datetime.utcnow()
        )
        db.add(tamper_flag)
        db.commit()
        return {"check_type": "metadata", "result": "NOT_APPLICABLE", "risk_level": "N/A", "details": details}


def ela_tamper_check(document_id: str, db: Session) -> Dict[str, Any]:
    """
    Error Level Analysis (ELA) Check:
    - Re-saves the image at JPEG quality=90.
    - Computes pixel-wise absolute difference between original and re-compressed version.
    - Amplifies difference (~18x) and generates an ELA color heatmap.
    - Computes regional variance statistics to detect localized compression anomalies.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    working_path = _resolve_path(doc.preprocessed_path or doc.file_path)
    if not working_path or not os.path.exists(working_path):
        raise ValueError(f"Image not found at {working_path}")

    img = cv2.imread(working_path)
    if img is None:
        raise ValueError(f"Failed to read image at {working_path}")

    # Re-save at JPEG quality=90
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
    success, encoded_img = cv2.imencode('.jpg', img, encode_params)
    if not success:
        raise ValueError("Failed to encode image for ELA")

    resaved_img = cv2.imdecode(encoded_img, cv2.IMREAD_COLOR)

    # Pixel-wise absolute difference
    diff = cv2.absdiff(img, resaved_img)

    # Amplify difference (18x)
    scale_factor = 18.0
    amplified = cv2.convertScaleAbs(diff, alpha=scale_factor, beta=0)

    # Create JET color heatmap for human visual inspection
    gray_diff = cv2.cvtColor(amplified, cv2.COLOR_BGR2GRAY)
    heatmap = cv2.applyColorMap(gray_diff, cv2.COLORMAP_JET)

    # Save heatmap image
    tamper_dir = _get_tamper_dir()
    heatmap_filename = f"{doc.id}_ela_heatmap.png"
    heatmap_rel_path = os.path.join(tamper_dir, heatmap_filename)
    cv2.imwrite(heatmap_rel_path, heatmap)

    # Regional Variance Analysis
    h, w = gray_diff.shape
    block_size = 64
    block_variances = []
    block_means = []

    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = gray_diff[y:y + block_size, x:x + block_size]
            block_variances.append(float(np.var(block)))
            block_means.append(float(np.mean(block)))

    if not block_variances:
        block_variances = [float(np.var(gray_diff))]
        block_means = [float(np.mean(gray_diff))]

    overall_mean_var = float(np.mean(block_variances))
    overall_mean_diff = float(np.mean(block_means))
    max_local_var = float(np.max(block_variances))
    variance_ratio = max_local_var / (overall_mean_var + 1e-6)

    is_uniformly_noisy = overall_mean_diff > 45.0 and variance_ratio < 2.0

    if variance_ratio >= 3.0 and max_local_var > 150.0:
        result = "SUSPICIOUS"
        risk_level = "HIGH"
    elif variance_ratio >= 2.0 and max_local_var > 75.0:
        result = "SUSPICIOUS"
        risk_level = "MEDIUM"
    else:
        result = "CLEAN"
        risk_level = "LOW"

    details = {
        "overall_mean_difference": round(overall_mean_diff, 2),
        "overall_mean_variance": round(overall_mean_var, 2),
        "max_local_variance": round(max_local_var, 2),
        "variance_ratio": round(variance_ratio, 2),
        "is_uniformly_noisy": is_uniformly_noisy,
        "heatmap_file": heatmap_rel_path,
        "disclaimer": "ELA is a heuristic signal, not proof of tampering — flag for human review only."
    }

    tamper_flag = TamperFlag(
        id=uuid.uuid4(),
        document_id=doc.id,
        check_type="ela",
        result=result,
        risk_level=risk_level,
        details=details,
        heatmap_path=heatmap_rel_path,
        created_at=datetime.utcnow()
    )
    db.add(tamper_flag)
    db.commit()

    return {
        "check_type": "ela",
        "result": result,
        "risk_level": risk_level,
        "heatmap_path": heatmap_rel_path,
        "details": details
    }

def run_tamper_checks(document_id: str, db: Session) -> Dict[str, Any]:
    """Runs both metadata and ELA tamper detection checks for a document."""
    db.query(TamperFlag).filter(TamperFlag.document_id == document_id).delete()
    db.commit()

    meta_res = metadata_tamper_check(document_id, db)
    ela_res = ela_tamper_check(document_id, db)

    overall_risk = "LOW"
    if meta_res.get("risk_level") == "HIGH" or ela_res.get("risk_level") == "HIGH":
        overall_risk = "HIGH"
    elif meta_res.get("risk_level") == "MEDIUM" or ela_res.get("risk_level") == "MEDIUM":
        overall_risk = "MEDIUM"

    return {
        "document_id": document_id,
        "overall_tamper_risk": overall_risk,
        "metadata_check": meta_res,
        "ela_check": ela_res
    }
