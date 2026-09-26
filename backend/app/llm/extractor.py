import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Document, OcrElement, ExtractedField

logger = logging.getLogger(__name__)

INVOICE_PROMPT_TEMPLATE = """You are an accurate Document Information Extraction system.
Your job is to extract structured data from OCR tokens of an INVOICE and cite the exact source OCR element ID(s) for every extracted field.

TARGET SCHEMA:
- seller (string | null): The seller / vendor company name or business issuing the invoice
- buyer (string | null): The buyer / client / customer name or company being billed
- invoice_no (string | null): Invoice number / reference ID
- invoice_date (string | null): Date of invoice issuance (YYYY-MM-DD if discernable, or raw date string)
- due_date (string | null): Payment due date
- subtotal (number | null): Subtotal amount before taxes
- tax (number | null): Total tax / VAT / GST / IGST amount
- total (number | null): Final total amount payable
- line_items (array of objects): Line items in the invoice table. Each line item must contain:
    - item (string | null): Product or service description
    - qty (number | null): Quantity
    - unit_price (number | null): Unit price / rate
    - line_total (number | null): Total price for this line item
    - source_element_ids (array of strings): The list of OCR element IDs corresponding to this line item

OCR TOKENS CONTEXT & RULES:
1. You are provided with a list of OCR elements: [{id, text, bbox, conf, region_type, row, col, heuristic_sourced}, ...]
2. IMPORTANT: `region_type` may be generic (e.g. "Region", "Text", "paragraph") rather than a specific semantic type. Use the text content and spatial bbox coordinates [x, y, w, h] to infer field roles. Do NOT rely on region_type alone.
3. IMPORTANT: Table cells where `heuristic_sourced` is true were grouped by a geometric heuristic and may contain imperfect row/col assignments. Always verify with the text and bbox positions.
4. CITATION REQUIREMENT: For EVERY field (seller, buyer, invoice_no, invoice_date, due_date, subtotal, tax, total, and each item in line_items), you MUST return:
   - "value": The extracted string or number, OR null if not present in the document.
   - "source_element_ids": A list of OCR token `id` strings from which the value was extracted.
5. NO HALLUCINATION RULE: If a field cannot be confidently located in the given OCR tokens, set its "value" to null and "source_element_ids" to []. DO NOT guess, extrapolate, or hallucinate values.
6. Return ONLY valid JSON matching the format below. No markdown backticks, no explanatory text.

OUTPUT FORMAT:
{
  "fields": {
    "seller": {"value": string | null, "source_element_ids": ["id", ...]},
    "buyer": {"value": string | null, "source_element_ids": ["id", ...]},
    "invoice_no": {"value": string | null, "source_element_ids": ["id", ...]},
    "invoice_date": {"value": string | null, "source_element_ids": ["id", ...]},
    "due_date": {"value": string | null, "source_element_ids": ["id", ...]},
    "subtotal": {"value": number | null, "source_element_ids": ["id", ...]},
    "tax": {"value": number | null, "source_element_ids": ["id", ...]},
    "total": {"value": number | null, "source_element_ids": ["id", ...]}
  },
  "line_items": [
    {
      "item": string | null,
      "qty": number | null,
      "unit_price": number | null,
      "line_total": number | null,
      "source_element_ids": ["id", ...]
    }
  ]
}
"""

SALARY_SLIP_PROMPT_TEMPLATE = """You are an accurate Document Information Extraction system.
Your job is to extract structured data from OCR tokens of a SALARY SLIP / PAYSLIP and cite the exact source OCR element ID(s) for every extracted field.

TARGET SCHEMA:
- employee_name (string | null): Name of the employee
- employer (string | null): Company / employer name
- pay_period (string | null): Pay period, month, or dates of pay
- gross (number | null): Gross pay / earnings
- deductions (number | null): Total deductions / taxes withheld
- net_pay (number | null): Net pay / take-home pay

OCR TOKENS CONTEXT & RULES:
1. You are provided with a list of OCR elements: [{id, text, bbox, conf, region_type, row, col, heuristic_sourced}, ...]
2. IMPORTANT: `region_type` may be generic (e.g. "Region", "Text", "paragraph"). Use the text content and spatial bbox coordinates [x, y, w, h] to infer field roles.
3. CITATION REQUIREMENT: For EVERY field, you MUST return:
   - "value": The extracted string or number, OR null if not present in the document.
   - "source_element_ids": A list of OCR token `id` strings from which the value was extracted.
4. NO HALLUCINATION RULE: If a field cannot be confidently located in the given OCR tokens, set its "value" to null and "source_element_ids" to []. DO NOT guess, extrapolate, or hallucinate values.
5. Return ONLY valid JSON matching the format below. No markdown backticks, no explanatory text.

OUTPUT FORMAT:
{
  "fields": {
    "employee_name": {"value": string | null, "source_element_ids": ["id", ...]},
    "employer": {"value": string | null, "source_element_ids": ["id", ...]},
    "pay_period": {"value": string | null, "source_element_ids": ["id", ...]},
    "gross": {"value": number | null, "source_element_ids": ["id", ...]},
    "deductions": {"value": number | null, "source_element_ids": ["id", ...]},
    "net_pay": {"value": number | null, "source_element_ids": ["id", ...]}
  }
}
"""

def _call_llm(system_prompt: str, user_content: str, strict_retry: bool = False) -> str:
    """Dispatches call to configured LLM (Anthropic Claude or OpenAI-compatible NVIDIA NIM)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    if strict_retry:
        messages.append({
            "role": "user", 
            "content": "CRITICAL ERROR: Your previous response was not valid JSON. Output RAW JSON ONLY. No markdown fences, no explanatory text outside { ... }."
        })

    if settings.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            temperature=0.0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}]
        )
        return response.content[0].text
    else:
        from openai import OpenAI
        client = OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY
        )
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=8192,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        msg = response.choices[0].message
        content = msg.content
        if not content and hasattr(msg, "reasoning_content"):
            content = getattr(msg, "reasoning_content", "")
        return content or ""

def _clean_json_response(raw_text: str) -> dict:
    """Strips markdown fences and extracts outermost JSON object."""
    text = raw_text.strip()
    if "```json" in text:
        parts = text.split("```json")
        if len(parts) > 1:
            text = parts[1].split("```")[0].strip()
    elif "```" in text:
        parts = text.split("```")
        if len(parts) > 1:
            text = parts[1].strip()
    
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx:end_idx + 1]
        
    return json.loads(text)

def extract_with_llm(document_id: str, db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Phase 4: LLM Schema Mapping + Source Citation
    1. Fetch document and ocr_elements (region_status != 'UNPROCESSABLE')
    2. Build prompt for doc_type with exact locked schema and OCR elements
    3. Call LLM (with 1 strict retry on JSON parsing failure)
    4. Persist structured results to extracted_fields with source_element_ids
    5. Update document status to LLM_EXTRACTED or LLM_EXTRACTION_FAILED
    """
    should_close_db = False
    if db is None:
        db = SessionLocal()
        should_close_db = True

    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found in database.")

        # Determine doc_type
        doc_type = doc.doc_type
        if not doc_type:
            fname = (doc.filename or "").lower()
            if "salary" in fname or "slip" in fname:
                doc_type = "salary_slip"
            else:
                doc_type = "invoice"
            doc.doc_type = doc_type

        # Fetch non-unprocessable OCR elements
        ocr_elements = (
            db.query(OcrElement)
            .filter(
                OcrElement.document_id == doc.id,
                OcrElement.region_status.in_(["OK", "PROCESSED"])
            )
            .all()
        )

        if not ocr_elements:
            logger.warning(f"No processable OCR elements found for document {doc.id}")
            doc.status = "LLM_EXTRACTION_FAILED"
            db.commit()
            return {"error": "No processable OCR elements found"}

        # Prepare tokens payload
        tokens_payload = []
        for el in ocr_elements:
            tokens_payload.append({
                "id": str(el.id),
                "text": el.text,
                "bbox": el.bbox,
                "conf": round(float(el.conf), 4),
                "region_type": el.region_type,
                "row": el.row,
                "col": el.col,
                "heuristic_sourced": bool(el.heuristic_sourced)
            })

        system_prompt = INVOICE_PROMPT_TEMPLATE if doc_type == "invoice" else SALARY_SLIP_PROMPT_TEMPLATE
        user_content = f"DOCUMENT_ID: {str(doc.id)}\nDOCUMENT_TYPE: {doc_type}\nOCR_ELEMENTS:\n{json.dumps(tokens_payload, indent=1)}"

        # Call LLM with 1 retry on malformed JSON
        parsed_result = None
        raw_response = ""
        for attempt in range(2):
            try:
                raw_response = _call_llm(
                    system_prompt=system_prompt,
                    user_content=user_content,
                    strict_retry=(attempt > 0)
                )
                parsed_result = _clean_json_response(raw_response)
                break
            except Exception as e:
                logger.warning(f"LLM extraction parse attempt {attempt+1} failed: {e}")
                if attempt == 1:
                    logger.error(f"LLM extraction failed after 2 attempts. Raw response: {raw_response[:300]}")
                    doc.status = "LLM_EXTRACTION_FAILED"
                    db.commit()
                    return {"error": "Malformed JSON from LLM extraction", "raw": raw_response}

        # Clear any prior extracted fields for this document
        db.query(ExtractedField).filter(ExtractedField.document_id == doc.id).delete()

        # Persist extracted scalar fields
        fields_dict = parsed_result.get("fields", {})
        db_fields = []
        for field_name, field_data in fields_dict.items():
            if isinstance(field_data, dict):
                val = field_data.get("value")
                cites = field_data.get("source_element_ids", [])
            else:
                val = field_data
                cites = []

            # Store in extracted_fields
            ext_field = ExtractedField(
                id=uuid.uuid4(),
                document_id=doc.id,
                field_name=field_name,
                extracted_value=str(val) if val is not None else None,
                source_element_ids=cites,
                line_item_group_id=None,
                extracted_at=datetime.utcnow()
            )
            db_fields.append(ext_field)

        # Persist line items if present (Invoice schema)
        # Choice: Each line item stored as a distinct row with a shared line_item_group_id
        # and field_name='line_item', storing item JSON in extracted_value and citing source_element_ids
        line_items = parsed_result.get("line_items", [])
        for idx, item in enumerate(line_items):
            group_id = f"item_{idx + 1}"
            cites = item.get("source_element_ids", [])
            item_payload = {
                "item": item.get("item"),
                "qty": item.get("qty"),
                "unit_price": item.get("unit_price"),
                "line_total": item.get("line_total")
            }
            line_field = ExtractedField(
                id=uuid.uuid4(),
                document_id=doc.id,
                field_name="line_item",
                extracted_value=json.dumps(item_payload),
                source_element_ids=cites,
                line_item_group_id=group_id,
                extracted_at=datetime.utcnow()
            )
            db_fields.append(line_field)

        db.add_all(db_fields)
        doc.status = "LLM_EXTRACTED"
        db.commit()

        logger.info(f"Successfully extracted {len(db_fields)} fields for document {doc.id}")
        return {
            "document_id": str(doc.id),
            "status": "LLM_EXTRACTED",
            "doc_type": doc_type,
            "fields_count": len(db_fields),
            "data": parsed_result
        }

    finally:
        if should_close_db:
            db.close()
