import os
import sys
import json
import cv2
import numpy as np

backend_dir = os.path.abspath('backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db.session import SessionLocal
from app.db.models import Document, OcrElement, ExtractedField, ValidationFlag, TamperFlag
from app.pipeline import run_end_to_end_pipeline, generate_full_report

def run_test():
    db = SessionLocal()
    try:
        # Document 1: Degraded Invoice (d8fb2fda-3ca7-498b-bce2-c10d18a2b62c or upload fresh)
        # Document 2: Salary Slip (dbc21d6c-97d8-4eb9-8b99-0ada48d4be87)
        test_docs = [
            {"id": "d8fb2fda-3ca7-498b-bce2-c10d18a2b62c", "label": "Degraded Invoice (Synthetic Sample)"},
            {"id": "dbc21d6c-97d8-4eb9-8b99-0ada48d4be87", "label": "Salary Slip (Clean Sample)"}
        ]

        reports = {}

        for item in test_docs:
            doc_id = item["id"]
            label = item["label"]
            print("\n" + "=" * 70)
            print(f"RUNNING COMPLETE PIPELINE PASS: {label} (ID: {doc_id})")
            print("=" * 70)

            # Execute end-to-end chain
            report = run_end_to_end_pipeline(doc_id, db)
            reports[doc_id] = report

            print(f"\nDOCUMENT STATUS: {report['status']}")
            print(f"TOTAL OCR ELEMENTS: {report['total_ocr_elements']}")

            print("\n--- EXTRACTED FIELDS & CONFIDENCE BREAKDOWN ---")
            for fname, fdata in report["extracted_fields"].items():
                print(f"  {fname:18} | Val: {str(fdata['value']):20} | Conf: {fdata['confidence']} (O:{fdata['ocr_confidence']} S:{fdata['string_similarity']} V:{fdata['validation_pass']}) | {fdata['review_status']}")

            if report["line_items"]:
                print(f"\n--- LINE ITEMS ({len(report['line_items'])} items) ---")
                for li in report["line_items"]:
                    print(f"  [{li['group_id']}] {li['data']} | Conf: {li['confidence']} | {li['review_status']}")

            print("\n--- VALIDATION FLAGS ---")
            for vf in report["validation_flags"]:
                print(f"  Rule: {vf['rule_name']:20} | Passed: {vf['passed']} | Details: {vf['details']}")

            print("\n--- TAMPER DETECTION FORENSICS ---")
            print(f"  Overall Tamper Risk: {report['tamper_detection']['overall_risk']}")
            for chk in report["tamper_detection"]["checks"]:
                print(f"  Check Type: {chk['check_type']:10} | Result: {chk['result']:15} | Risk: {chk['risk_level']}")
                print(f"    Details: {chk['details']}")
                if chk.get("heatmap_path"):
                    print(f"    Heatmap Path: {chk['heatmap_path']}")
                    # Verify heatmap exists on disk
                    exists = os.path.exists(chk["heatmap_path"])
                    size = os.path.getsize(chk["heatmap_path"]) if exists else 0
                    print(f"    Heatmap Verification: Exists={exists}, Size={size} bytes")

        print("\n" + "=" * 70)
        print("SUMMARY EVALUATION & COMPARATIVE ELA HEATMAP ANALYSIS")
        print("=" * 70)
        for doc_id, r in reports.items():
            ela = next((c for c in r["tamper_detection"]["checks"] if c["check_type"] == "ela"), None)
            meta = next((c for c in r["tamper_detection"]["checks"] if c["check_type"] == "metadata"), None)
            print(f"\nDoc: {r['filename']} ({r['doc_type']})")
            print(f"  Metadata Check : {meta['result']} (Risk: {meta['risk_level']}) - Reason: {meta['details'].get('reason') or 'PDF inspected'}")
            if ela:
                d = ela["details"]
                print(f"  ELA Analysis   : {ela['result']} (Risk: {ela['risk_level']})")
                print(f"    - Overall Mean Difference: {d['overall_mean_difference']}")
                print(f"    - Max Local Variance     : {d['max_local_variance']}")
                print(f"    - Variance Ratio         : {d['variance_ratio']}")
                print(f"    - Uniform Noise Detected : {d['is_uniformly_noisy']}")
                if d['is_uniformly_noisy']:
                    print(f"    -> NOTE: Elevated ELA noise floor is UNIFORM across entire sample (typical of synthetic noise / whole-image recompression), not a localized forgery.")

        # Save full reports JSON
        with open("full_pipeline_reports.json", "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2)
        print("\nFull report JSON successfully written to full_pipeline_reports.json")

    finally:
        db.close()

if __name__ == "__main__":
    run_test()
