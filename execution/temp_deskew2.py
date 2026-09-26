import cv2
import numpy as np

def test_deskew_median(path):
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return 0.0
    
    angles = []
    for c in contours:
        if len(c) < 5: continue
        rect = cv2.minAreaRect(c)
        (w, h) = rect[1]
        if w < 10 or h < 10: continue
        
        angle = rect[-1]
        if w < h:
            angle = angle - 90
        
        if angle > 45:
            angle -= 90
        elif angle < -45:
            angle += 90
            
        angles.append(angle)
        
    if not angles: return 0.0
    
    # Return median angle
    return np.median(angles)

print("Clean slip angle:", test_deskew_median("../.tmp/samples/clean_salary_slip.png"))
print("Degraded invoice angle:", test_deskew_median("../.tmp/samples/degraded_invoice.jpg"))
