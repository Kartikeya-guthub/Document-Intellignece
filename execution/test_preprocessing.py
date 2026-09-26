import os
import sys

# Setup paths relative to the execution script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
from app.preprocessing.pipeline import preprocess_document, convert_pdf_to_image

def run_tests():
    sample_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.tmp', 'samples'))
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.tmp', 'preprocessed_output'))
    os.makedirs(sample_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Checking for samples in {sample_dir}...")
    files = os.listdir(sample_dir)
    if not files:
        print("No samples found. Please place your degraded invoice and clean salary slip in:")
        print(f"  {sample_dir}")
        print("Then run this script again to see visual outputs.")
        return
        
    for file in files:
        in_path = os.path.join(sample_dir, file)
        out_path = os.path.join(out_dir, f"preprocessed_{file}.png")
        
        try:
            if file.lower().endswith(".pdf"):
                img_path = os.path.join(out_dir, f"raw_converted_{file}.png")
                in_path = convert_pdf_to_image(in_path, img_path)
                
            print(f"Processing {file}...")
            final_out, meta = preprocess_document(in_path, out_path)
            print(f"Success! Saved to {final_out}. Meta: {meta}")
        except Exception as e:
            print(f"Error processing {file}: {e}")

if __name__ == "__main__":
    run_tests()
