import cv2
import numpy as np
import os

def create_degraded_invoice():
    img = np.ones((800, 600, 3), dtype=np.uint8) * 255
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, "INVOICE #12345", (50, 100), font, 1.5, (0, 0, 0), 2)
    cv2.putText(img, "Date: 2026-09-26", (50, 150), font, 0.8, (0, 0, 0), 1)
    cv2.putText(img, "Item: Server Rack  ", (50, 250), font, 1, (0, 0, 0), 2)
    cv2.putText(img, "Item: Networking  ", (50, 300), font, 1, (0, 0, 0), 2)
    cv2.putText(img, "Total: ", (50, 400), font, 1.2, (0, 0, 0), 2)
    
    # Skew by 3 degrees
    M = cv2.getRotationMatrix2D((300, 400), 3, 1)
    skewed = cv2.warpAffine(img, M, (600, 800), borderValue=(255,255,255))
    
    # Add noise
    noise = np.random.normal(0, 25, skewed.shape).astype(np.uint8)
    degraded = cv2.add(skewed, noise)
    
    cv2.imwrite("../.tmp/samples/degraded_invoice.jpg", degraded)

def create_clean_salary_slip():
    img = np.ones((600, 800, 3), dtype=np.uint8) * 255
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, "SALARY SLIP", (300, 50), font, 1.2, (0, 0, 0), 2)
    cv2.putText(img, "Employee: Jane Doe", (50, 150), font, 0.8, (0, 0, 0), 1)
    cv2.putText(img, "Gross Pay: ", (50, 250), font, 0.8, (0, 0, 0), 1)
    cv2.putText(img, "Deductions: ", (50, 300), font, 0.8, (0, 0, 0), 1)
    cv2.putText(img, "Net Pay: ", (50, 400), font, 1, (0, 0, 0), 2)
    
    cv2.imwrite("../.tmp/samples/clean_salary_slip.png", img)

os.makedirs("../.tmp/samples", exist_ok=True)
create_degraded_invoice()
create_clean_salary_slip()
print("Generated samples.")
