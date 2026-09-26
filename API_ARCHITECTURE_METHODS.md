# 🛠️ API & Feature Architecture Guide: Methods & Techniques

This reference document outlines the **exact algorithms, libraries, mathematical formulas, and methods** used at every API level and feature in the Document Intelligence pipeline.

---

## 📌 Quick Summary Table

| API Level / Feature | Method / Algorithm Used | Libraries & Tools | Key Thresholds / Formulas |
| :--- | :--- | :--- | :--- |
| **1. Upload & Duplicate Check** | SHA-256 Hashing + DB lookup | `hashlib`, `PostgreSQL` | Byte-level exact match |
| **2. Preprocessing** | Affine Deskewing + Bilateral Filter | `OpenCV (cv2)`, `PyMuPDF` | $\theta \in [-45^{\circ}, 45^{\circ}]$ rotation |
| **3. OCR & Layout** | GPU Deep Learning Det & Rec | `PaddleOCR (PP-OCRv5)`, `CUDA 12.3` | Floor Conf $\ge 0.30$, `UNPROCESSABLE` gate |
| **4. Table Structure** | Spatial Grid Heuristic | Custom coordinate clustering | Row/Col bins, `heuristic_sourced=true` |
| **5. LLM Extraction** | JSON Schema Mapping + Citation | `NVIDIA NIM (Nemotron-3-Ultra)` | Mandatory `source_element_ids` citation |
| **6. Validation** | Deterministic Arithmetic & Dates | Python float math & ISO 8601 | $\text{Subtotal} + \text{Tax} == \text{Total}$ |
| **7. Confidence Engine** | Multi-Factor Linear Combination | `python-Levenshtein` | $0.5 \cdot O + 0.3 \cdot S + 0.2 \cdot V$ (Cap $\le 0.5$ if $V=0$) |
| **8. Forensic Tamper (Metadata)**| PDF Producer & Timestamp Forensics | `PyMuPDF (fitz)` | ModDate > CreationDate; Editing regex |
| **9. Forensic Tamper (ELA)** | Error Level Analysis (JPEG Q=90) | `OpenCV (cv2)`, `NumPy` | Variance Ratio $\ge 3.0 \rightarrow \text{HIGH}$ Risk |
| **10. Full-Report & Serving** | Unified JSON Aggregation + StaticMount| `FastAPI`, `Starlette StaticFiles` | Single-response retrieval |

---

## 🔬 Detailed Breakdown by Feature & API Level

### 1. Ingestion & Preprocessing
* **Trigger Endpoint:** `POST /api/v1/documents/upload`
* **File Normalization:** 
  - If PDF: Rasterized to 300 DPI image via `fitz.open()` and `pix.pil_tobytes("png")`.
* **Deskewing (Orientation Correction):**
  - Converts image to grayscale $\rightarrow$ Otsu thresholding $\rightarrow$ `cv2.minAreaRect()` computes bounding angle $\theta$.
  - Generates affine rotation matrix via `cv2.getRotationMatrix2D()` to level the page horizontally.
* **Denoising:**
  - `cv2.bilateralFilter(d=9, sigmaColor=75, sigmaSpace=75)` preserves sharp character edges while flattening paper grain.
* **Byte Duplication:**
  - Computes `hashlib.sha256(file_bytes).hexdigest()`. Rejects or flags duplicate uploads before running heavier models.

---

### 2. OCR & Table Layout Detection
* **Trigger Endpoint:** `POST /api/v1/documents/{doc_id}/process` (or auto via `upload`)
* **Inspection Endpoint:** `GET /api/v1/documents/{doc_id}/ocr`
* **GPU OCR Engine:**
  - PaddleOCR with `PP-OCRv5_server_det` (text line detection) and `PP-OCRv5_server_rec` (text recognition) running on CUDA GPU (`device="gpu:0"`).
  - Inference speed: **`0.80s`** warm execution time.
* **Quality Gate:**
  - Every detected box has confidence score $c \in [0.0, 1.0]$.
  - If $c < 0.30$: Tagged as `region_status = "UNPROCESSABLE"` and shielded from the LLM to avoid garbage tokens.
* **Table Extraction (Spatial Grid Heuristic):**
  - If native wired table recognition yields empty structures, `infer_table_grid()` clusters elements into horizontal $(Y)$ row bands and vertical $(X)$ column bins.
  - Formats elements into a 2D matrix and assigns `heuristic_sourced = true` for auditing.

---

### 3. LLM Schema Extraction & Source Citation
* **Trigger Endpoint:** `POST /api/v1/documents/{doc_id}/extract`
* **Inspection Endpoint:** `GET /api/v1/documents/{doc_id}/fields`
* **AI Model:** NVIDIA NIM `nvidia/nemotron-3-ultra-550b-a55b` (or OpenAI/Claude).
* **Technique:**
  - Only valid OCR elements (`region_status == "OK"`) are provided in the prompt.
  - Strictly typed Pydantic models: `InvoiceSchema` and `SalarySlipSchema`.
* **Zero-Hallucination Citation Rule:**
  - For every extracted field, the LLM must return the array of OCR IDs: `source_element_ids: [12, 14]`.
  - If a value cannot be found in the OCR boxes (e.g. missing `due_date`), it **must** return `value: null` with `source_element_ids: []`.
  - Unfound fields are added to `could_not_extract`.

---

### 4. Deterministic Validation Engine
* **Executed automatically** after extraction.
* **Rule 1 (Invoice Math):**
  $$|\text{Subtotal} + \text{Tax} - \text{Total}| \le 0.05$$
* **Rule 2 (Salary Slip Math):**
  $$|\text{Gross Earnings} - \text{Total Deductions} - \text{Net Pay}| \le 0.05$$
* **Rule 3 (Date Ordering):**
  $$\text{Due Date} \ge \text{Invoice Date}$$
* **Output:** Stored in `validation_flags` table with exact delta mismatch (e.g., `difference: 732000`).

---

### 5. Multi-Factor Confidence Engine
* **Formula:**
  $$\text{Confidence} = 0.5 \cdot O + 0.3 \cdot S + 0.2 \cdot V$$
  - $O$ = Mean OCR confidence of cited source bounding boxes.
  - $S$ = Levenshtein string similarity between normalized value and cited raw text:
    $$S = 1.0 - \frac{\text{LevenshteinDistance}(\text{extracted}, \text{cited})}{\max(\text{len}(\text{extracted}), \text{len}(\text{cited}))}$$
  - $V$ = Validation pass ($1.0$ if passed, $0.0$ if failed).
* **Hard Clamping Constraint:**
  $$\text{If } V = 0 \implies \text{Confidence} = \min(\text{Confidence}, 0.50)$$
* **Review Routing:**
  - $\text{Confidence} \ge 0.70 \implies \text{auto\_accepted}$
  - $\text{Confidence} < 0.70 \implies \text{needs\_review}$

---

### 6. Forensic Tamper Detection
* **Trigger Endpoint:** `POST /api/v1/documents/{doc_id}/tamper`
* **Inspection Endpoint:** `GET /api/v1/documents/{doc_id}/tamper`
* **Method A: PDF Metadata Forensics**
  - Uses `fitz.open()` to extract `CreationDate`, `ModDate`, `Producer`, and `Creator`.
  - Flags `SUSPICIOUS` if:
    1. `ModDate > CreationDate` (document modified post-generation).
    2. `Producer` contains editing signatures (*Photoshop, Acrobat Pro, GIMP, InDesign, Canva*).
  - If input is an image (JPG/PNG): Returns `NOT_APPLICABLE` (honest reporting, no fake pass).
* **Method B: Error Level Analysis (ELA)**
  1. Re-compresses image in memory at JPEG Quality 90:
     `cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])`.
  2. Calculates absolute difference: $\Delta = |\text{Original} - \text{Recompressed}|$.
  3. Amplifies difference by $18\times$: `cv2.convertScaleAbs(diff, alpha=18.0)`.
  4. Renders JET colormap heatmap (`cv2.applyColorMap(gray, cv2.COLORMAP_JET)`).
  5. Computes statistical grid variance across $64 \times 64$ blocks:
     $$\text{Variance Ratio} = \frac{\max(\sigma^2_{\text{local}})}{\text{mean}(\sigma^2_{\text{overall}})}$$
  6. **Threshold Rules:**
     - Ratio $\ge 3.0$ and Max Local Variance $> 150 \implies \mathbf{\text{SUSPICIOUS (HIGH RISK)}}$
     - Ratio $\ge 2.0$ and Max Local Variance $> 75 \implies \mathbf{\text{SUSPICIOUS (MEDIUM RISK)}}$
     - Ratio $< 2.0 \implies \mathbf{\text{CLEAN (LOW RISK)}}$
     - Mean Difference $> 45$ and Ratio $< 2.0 \implies \mathbf{\text{Uniformly Noisy}}$ (Camera grain/synthetic noise disclaimer).

---

### 7. Unified Full-Report API
* **Endpoint:** `GET /api/v1/documents/{doc_id}/full-report`
* **Response Payload:** Aggregates everything in one call:
  1. Document Metadata (`id`, `filename`, `doc_type`, `status`)
  2. Direct Image URLs (`preprocessed_image_url`, `heatmap_url`)
  3. Duplication Info (SHA-256 match + semantic invoice number check)
  4. Extracted Fields (Values, $(O,S,V)$ breakdown, review flags, source citations)
  5. Line Items (Structured tabular items with row group IDs)
  6. Could Not Extract list
  7. Deterministic Validation Flags
  8. Tamper Detection Risk & ELA Statistics
