import os
import sys
import json

backend_dir = os.path.abspath('backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.llm.extractor import extract_with_llm
from app.db.session import SessionLocal
from app.db.models import Document, ExtractedField, OcrElement

def verify_citations(doc_id: str, doc_name: str, result_data: dict, db) -> bool:
    print(f"\n=======================================================")
    print(f"VERIFYING CITATIONS FOR: {doc_name} (ID: {doc_id})")
    print(f"=======================================================")
    
    fields = result_data.get("fields", {})
    all_passed = True
    citation_count = 0
    total_non_null_fields = 0

    print("\n--- Scalar Fields ---")
    for fname, fdata in fields.items():
        if isinstance(fdata, dict):
            val = fdata.get("value")
            cites = fdata.get("source_element_ids", [])
        else:
            val = fdata
            cites = []
        
        has_val = val is not None
        if has_val:
            total_non_null_fields += 1
            has_cite = len(cites) > 0
            if has_cite:
                citation_count += 1
                status = "PASS (Cited)"
            else:
                status = "FAIL (HALLUCINATION DETECTED: non-null value with 0 citations!)"
                all_passed = False
        else:
            status = "NULL (Correctly null with empty citations)" if len(cites) == 0 else "WARN (Null with citations)"

        print(f"  {fname:15} = {str(val):30} | Cites: {len(cites)} | Status: {status}")
        if cites:
            print(f"     -> Citation IDs: {cites[:3]}{'...' if len(cites) > 3 else ''}")

    line_items = result_data.get("line_items", [])
    if line_items:
        print("\n--- Line Items ---")
        for idx, item in enumerate(line_items):
            cites = item.get("source_element_ids", [])
            has_item = any(item.get(k) is not None for k in ["item", "qty", "unit_price", "line_total"])
            if has_item:
                total_non_null_fields += 1
                if cites:
                    citation_count += 1
                    status = "PASS (Cited)"
                else:
                    status = "FAIL (HALLUCINATION DETECTED: line item has values but 0 citations!)"
                    all_passed = False
            else:
                status = "EMPTY"
            print(f"  Item #{idx+1:2}: {item.get('item', ''):25} Qty: {str(item.get('qty', '')):5} Total: {str(item.get('line_total', '')):8} | Cites: {len(cites)} | {status}")
            if cites:
                print(f"     -> Citation IDs: {cites[:3]}{'...' if len(cites) > 3 else ''}")

    # Verify rows persisted in DB
    db_fields = db.query(ExtractedField).filter(ExtractedField.document_id == doc_id).all()
    print(f"\nDB Verification:")
    print(f"  Total ExtractedField rows in DB: {len(db_fields)}")
    for df in db_fields[:5]:
        print(f"    - {df.field_name}: '{df.extracted_value}' | cites: {len(df.source_element_ids or [])} | group_id: {df.line_item_group_id}")
    if len(db_fields) > 5:
        print(f"    ... and {len(db_fields) - 5} more rows.")

    print(f"\nResult: {'ALL CITATIONS VALID (0 Hallucinations)' if all_passed else 'CITATION VERIFICATION FAILED'}")
    print(f"Total Non-Null Fields: {total_non_null_fields}, Validly Cited: {citation_count}")
    return all_passed

def main():
    test_docs = [
        {"id": "d2f502bc-5f7e-42e1-b5e5-36269018a705", "name": "Invoice (minimal-yellow-invoice)"},
        {"id": "dbc21d6c-97d8-4eb9-8b99-0ada48d4be87", "name": "Salary Slip (salary-slip-format)"}
    ]

    db = SessionLocal()
    try:
        all_success = True
        for t in test_docs:
            doc_id = t["id"]
            doc_name = t["name"]
            print(f"\n=======================================================")
            print(f"RUNNING EXTRACT_WITH_LLM ON: {doc_name}")
            print(f"=======================================================")
            
            res = extract_with_llm(doc_id, db=db)
            if "error" in res:
                print(f"Extraction failed for {doc_name}: {res['error']}")
                all_success = False
                continue

            passed = verify_citations(doc_id, doc_name, res.get("data", {}), db)
            if not passed:
                all_success = False

        print("\n=======================================================")
        if all_success:
            print("PHASE 4 LLM EXTRACTION & CITATION TEST: PASSED COMPLETELY!")
        else:
            print("PHASE 4 LLM EXTRACTION & CITATION TEST: FAILED (Review output above)")
        print("=======================================================")

    finally:
        db.close()

if __name__ == "__main__":
    main()
