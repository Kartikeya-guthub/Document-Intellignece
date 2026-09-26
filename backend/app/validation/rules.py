import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.db.models import ValidationFlag

logger = logging.getLogger(__name__)

def _to_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        cleaned = str(val).replace("$", "").replace("₹", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def _parse_date(val: Any) -> Optional[datetime]:
    if not val:
        return None
    for fmt in [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d-%B-%Y",
        "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%Y"
    ]:
        try:
            return datetime.strptime(str(val).strip(), fmt)
        except ValueError:
            pass
    return None

def run_validation_rules(doc_type: str, extracted_fields: Dict[str, Any]) -> Dict[str, int]:
    """
    Evaluates business and mathematical validation rules.
    Returns:
        Dict mapping field_name -> binary validation pass V (1 if passed / not violated, 0 if failed).
    """
    v_scores: Dict[str, int] = {}
    for f in extracted_fields.keys():
        v_scores[f] = 1

    if doc_type == "invoice":
        subtotal = _to_float(extracted_fields.get("subtotal"))
        tax = _to_float(extracted_fields.get("tax"))
        total = _to_float(extracted_fields.get("total"))

        if subtotal is not None and tax is not None and total is not None:
            expected_total = subtotal + tax
            diff = abs(expected_total - total)
            if diff > 0.05:
                v_scores["subtotal"] = 0
                v_scores["tax"] = 0
                v_scores["total"] = 0

        inv_date = _parse_date(extracted_fields.get("invoice_date"))
        due_date = _parse_date(extracted_fields.get("due_date"))
        if inv_date and due_date:
            if due_date < inv_date:
                v_scores["due_date"] = 0
                v_scores["invoice_date"] = 0

    elif doc_type == "salary_slip":
        gross = _to_float(extracted_fields.get("gross"))
        deductions = _to_float(extracted_fields.get("deductions"))
        net_pay = _to_float(extracted_fields.get("net_pay"))

        if gross is not None and deductions is not None and net_pay is not None:
            expected_net = gross - deductions
            diff = abs(expected_net - net_pay)
            if diff > 0.05:
                v_scores["gross"] = 0
                v_scores["deductions"] = 0
                v_scores["net_pay"] = 0

    return v_scores

def validate_field(field_name: str, field_value: Any, all_fields: Dict[str, Any], doc_type: str) -> bool:
    """Evaluates whether an individual field passes validation."""
    scores = run_validation_rules(doc_type, all_fields)
    return scores.get(field_name, 1) == 1

def persist_validation_flags(
    document_id: str,
    doc_type: str,
    fields_dict: Dict[str, Any],
    db: Session
) -> List[Dict[str, Any]]:
    """Runs validation rules and stores ValidationFlag rows in the database."""
    flags_summary = []
    db.query(ValidationFlag).filter(ValidationFlag.document_id == document_id).delete()

    if doc_type == "invoice":
        subtotal = _to_float(fields_dict.get("subtotal"))
        tax = _to_float(fields_dict.get("tax"))
        total = _to_float(fields_dict.get("total"))
        
        passed_math = True
        details = {}
        if subtotal is not None and tax is not None and total is not None:
            expected = subtotal + tax
            diff = abs(expected - total)
            passed_math = diff <= 0.05
            details = {"subtotal": subtotal, "tax": tax, "total": total, "expected": expected, "difference": round(diff, 2)}
        else:
            details = {"note": "One or more amounts missing, arithmetic check not applicable"}

        flag = ValidationFlag(
            id=uuid.uuid4(),
            document_id=document_id,
            field_name="total",
            rule_name="subtotal_tax_sum",
            passed=passed_math,
            details=details,
            created_at=datetime.utcnow()
        )
        db.add(flag)
        flags_summary.append({"rule": "subtotal_tax_sum", "passed": passed_math, "details": details})

        inv_date = _parse_date(fields_dict.get("invoice_date"))
        due_date = _parse_date(fields_dict.get("due_date"))
        if inv_date and due_date:
            passed_date = due_date >= inv_date
            details_date = {"invoice_date": str(inv_date.date()), "due_date": str(due_date.date())}
        else:
            passed_date = True
            details_date = {"note": "Due date not present or unparsed, rule passed"}
            
        flag_date = ValidationFlag(
            id=uuid.uuid4(),
            document_id=document_id,
            field_name="due_date",
            rule_name="due_after_invoice",
            passed=passed_date,
            details=details_date,
            created_at=datetime.utcnow()
        )
        db.add(flag_date)
        flags_summary.append({"rule": "due_after_invoice", "passed": passed_date, "details": details_date})

    elif doc_type == "salary_slip":
        gross = _to_float(fields_dict.get("gross"))
        deductions = _to_float(fields_dict.get("deductions"))
        net_pay = _to_float(fields_dict.get("net_pay"))

        passed_net = True
        details_net = {}
        if gross is not None and deductions is not None and net_pay is not None:
            expected_net = gross - deductions
            diff = abs(expected_net - net_pay)
            passed_net = diff <= 0.05
            details_net = {"gross": gross, "deductions": deductions, "net_pay": net_pay, "expected_net": expected_net, "difference": round(diff, 2)}
        else:
            details_net = {"note": "One or more pay amounts missing"}

        flag_salary = ValidationFlag(
            id=uuid.uuid4(),
            document_id=document_id,
            field_name="net_pay",
            rule_name="gross_deductions_net",
            passed=passed_net,
            details=details_net,
            created_at=datetime.utcnow()
        )
        db.add(flag_salary)
        flags_summary.append({"rule": "gross_deductions_net", "passed": passed_net, "details": details_net})

    db.commit()
    return flags_summary
