import os
import sys
import cv2

backend_dir = os.path.abspath('backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.ocr.engine import run_ocr_and_layout

def main():
    samples = [
        "clean_salary_slip.png",
        "degraded_invoice.jpg"
    ]
    
    for sample in samples:
        print(f"\n--- Testing {sample} ---")
        img_path = f".tmp/samples/{sample}"
            
        print(f"Loading {img_path}...")
        img = cv2.imread(img_path)
        if img is None:
            print(f"Could not load image: {img_path}")
            continue
            
        print("Running OCR + Layout pipeline...")
        try:
            elements = run_ocr_and_layout(img, doc_id=1)
            
            print(f"\nStats for {sample}:")
            print(f"Total elements extracted: {len(elements)}")
            
            unprocessable_count = sum(1 for e in elements if e.get("region_status") == "UNPROCESSABLE")
            print(f"UNPROCESSABLE count: {unprocessable_count}")
            
            tables_count = sum(1 for e in elements if e.get("region_type") in ("table", "table_cell"))
            print(f"Table cells count: {tables_count}")
            
            if elements:
                print("\nSample element:")
                print(elements[0])
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"FAILED: {e}")

if __name__ == "__main__":
    main()
