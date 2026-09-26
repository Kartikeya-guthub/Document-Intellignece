import os
import cv2
import numpy as np
import pymupdf as fitz  # PyMuPDF
from typing import Tuple


def convert_pdf_to_image(pdf_path: str, output_path: str) -> str:
    """Converts the first page of a PDF to an image using PyMuPDF."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)  # Single-page assumption
    pix = page.get_pixmap(dpi=300)
    pix.save(output_path)
    doc.close()
    return output_path


def preprocess_document(input_path: str, output_path: str) -> Tuple[str, dict]:
    """
    Fixed preprocessing pipeline applied to every uploaded image.

    Pipeline (order is locked for Phase 2):
      1. Grayscale conversion
      2. Deskew  - Otsu on throwaway copy -> contours -> minAreaRect median angle
                    -> warpAffine if |angle| > 0.5 deg
      3. Denoise  - fastNlMeansDenoising h=5  (conservative; preserves thin strokes)
      4. CLAHE    - clipLimit=1.5, tileGridSize=(8,8)  (mild; avoids amplifying noise)
      5. Background normalization  - morphological closing with large kernel (~10% of
                    image size) estimates slowly-varying background shading and colored
                    fills; dividing by it maps every region to a uniform white canvas
                    so adaptive threshold sees only ink, not header color fills.
      6. Adaptive Threshold - GAUSSIAN_C, blockSize=51, C=15
                    (large window = whole character regions evaluated, not noise patches;
                     high C = strong contrast required before a pixel is marked as ink)
    """
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Could not read image at {input_path}")

    # Step 1: Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Step 2: Deskew
    _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(t, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angle = 0.0
    angles = []
    for c in contours:
        if len(c) < 5:
            continue
        rect = cv2.minAreaRect(c)
        w, h = rect[1]
        if w < 10 or h < 10:
            continue
        a = rect[-1]
        if w < h:
            a -= 90
        if a > 45:
            a -= 90
        elif a < -45:
            a += 90
        angles.append(a)
    if angles:
        angle = float(np.median(angles))
        if abs(angle) > 0.5:
            h_img, w_img = gray.shape[:2]
            M = cv2.getRotationMatrix2D((w_img // 2, h_img // 2), angle, 1.0)
            gray = cv2.warpAffine(
                gray, M, (w_img, h_img),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )

    # Step 3: Denoise - h=5 (conservative; preserves thin text strokes)
    denoised = cv2.fastNlMeansDenoising(
        gray, None, h=5, searchWindowSize=21, templateWindowSize=7
    )

    # Step 4: CLAHE - clipLimit=1.5 (mild; avoids amplifying background noise)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    # Step 5: Background normalization via morphological closing.
    # The large structuring element (~10% of image size) only fits over broad bright
    # regions (white page, light fills, blue/gray headers), producing a background map.
    # Dividing the enhanced image by this map stretches every local region to full
    # dynamic range, so colored or shaded table headers look identical to white paper
    # from the perspective of the adaptive thresholder below.
    ks = max(img.shape[:2]) // 10 | 1  # ~10% of image, forced odd
    bg_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (ks, ks))
    background = cv2.morphologyEx(enhanced, cv2.MORPH_CLOSE, bg_kernel)
    normalized = cv2.divide(enhanced, background, scale=255)

    # Step 6: Adaptive Threshold
    # blockSize=51: wide window evaluates full character regions, not noise patches
    # C=15: high constant requires strong contrast before classifying a pixel as ink
    binarized = cv2.adaptiveThreshold(
        normalized, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=51,
        C=15,
    )

    cv2.imwrite(output_path, binarized)
    return output_path, {"deskew_angle": angle}
