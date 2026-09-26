import cv2
import numpy as np
import os

def create_comparison(img1_path, img2_path, out_path, title1="Before", title2="After"):
    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)
    
    # Ensure they have the same height
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    max_h = max(h1, h2)
    
    img1_resized = cv2.resize(img1, (int(w1 * max_h / h1), max_h))
    img2_resized = cv2.resize(img2, (int(w2 * max_h / h2), max_h))
    
    # Add title bars
    bar1 = np.ones((50, img1_resized.shape[1], 3), dtype=np.uint8) * 200
    cv2.putText(bar1, title1, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    img1_with_bar = np.vstack((bar1, img1_resized))
    
    bar2 = np.ones((50, img2_resized.shape[1], 3), dtype=np.uint8) * 200
    cv2.putText(bar2, title2, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    img2_with_bar = np.vstack((bar2, img2_resized))
    
    combined = np.hstack((img1_with_bar, img2_with_bar))
    cv2.imwrite(out_path, combined)
    print(f"Saved comparison to {out_path}")

base = "C:/Users/Lenovo/Desktop/Document Intelligence/.tmp"
create_comparison(
    os.path.join(base, "samples", "degraded_invoice.jpg"),
    os.path.join(base, "preprocessed_output", "preprocessed_degraded_invoice.jpg.png"),
    os.path.join(base, "preprocessed_output", "comparison_invoice.png")
)
create_comparison(
    os.path.join(base, "samples", "clean_salary_slip.png"),
    os.path.join(base, "preprocessed_output", "preprocessed_clean_salary_slip.png.png"),
    os.path.join(base, "preprocessed_output", "comparison_salary.png")
)
