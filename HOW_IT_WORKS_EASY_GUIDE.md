# 📄 How It Works: The Simple Step-by-Step Guide

Imagine your invoice or salary slip is placed on a **factory conveyor belt**. From the moment you click **Upload**, it travels through **7 inspection checkpoints** before deciding: *"Can we trust this document, or does a human need to inspect it?"*

---

```
  [ 📤 Upload Document ]
             │
             ▼
   Station 1: The Clean-Up Station (Straighten & clean paper)
             │
             ▼
   Station 2: The Eye (Read words & identify tables)
             │
             ▼
   Station 3: The Brain (Understand who is seller, buyer, and total)
             │
             ▼
   Station 4: The Accountant (Verify if the math adds up)
             │
             ▼
   Station 5: The Trust Meter (Calculate confidence score 0% - 100%)
             │
             ▼
   Station 6: The Forensic Detective (X-ray pixels to catch edits & Photoshop)
             │
             ▼
   Station 7: The Final Verdict (Auto-Approve or Route to Human)
```

---

## 🧼 Station 1: The Clean-Up Station (Ingestion & Preprocessing)

### What it does:
1. **Digital Fingerprint (Duplicate Check):** Checks if this exact file was already uploaded earlier.
2. **Straighten the Paper (Deskewing):** Automatically rotates tilted or crooked scans so all text lines are horizontal.
3. **Remove Background Noise:** Wipes away scanner grain, shadows, and speckles so text edges are crisp.

### ⚙️ How it works (Under the hood):
* **Fingerprint:** Calculates a unique **SHA-256 byte hash** (like an MD5 checksum) of the file and instantly checks the database for a match.
* **Deskewing:** Uses **OpenCV** to detect the minimum bounding rectangle angle of the page and applies an **affine rotation matrix** to spin it straight.
* **Cleaning:** Applies a **bilateral filter** that smooths flat background noise while keeping sharp text edges untouched.

---

## 👁️ Station 2: The Eye (OCR & Table Detection)

### What it does:
1. **Reads Words:** Scans the page and draws a bounding box around every word and number.
2. **The "Blurry" Safety Filter:** Stamps faded or illegible words as **`UNPROCESSABLE`** so the AI is never fed blurry garbage.
3. **Rebuilds Tables:** Organizes scattered cells into structured rows and columns.

### ⚙️ How it works (Under the hood):
* **OCR Engine:** Uses **PaddleOCR on NVIDIA GPU**, running deep neural networks (`PP-OCRv5`) to detect and recognize text in under 1 second.
* **Confidence Gate:** Any word box scoring below **30% confidence** is automatically filtered out before reaching the AI.
* **Table Reconstruction:** A **spatial grid clustering algorithm** groups text boxes sharing similar horizontal $(Y)$ coordinates into rows and vertical $(X)$ coordinates into columns.

---

## 🧠 Station 3: The Brain (LLM Understanding)

### What it does:
1. **Understands Meaning:** Extracts key data points (Seller, Buyer, Invoice Number, Dates, Totals).
2. **The Anti-Lying Rule (Mandatory Citation):** The AI is **forbidden from guessing**. It must cite the exact box ID where it found each number. If a date is not on the page, it must honestly say **"Not Found"**.

### ⚙️ How it works (Under the hood):
* **AI Model:** Uses an advanced reasoning model (**NVIDIA Nemotron AI**) via an OpenAI-compatible API.
* **Strict JSON Template:** The prompt enforces strict **Pydantic schemas** (`InvoiceSchema` / `SalarySlipSchema`).
* **Source Citation:** The model is instructed to output `source_element_ids: [12, 14]` alongside each field. Any value without a valid OCR box citation is rejected.

---

## 🧮 Station 4: The Accountant (Math Validation)

### What it does:
The system opens an automated calculator to verify that the document's own internal math adds up:
* **Invoices:** Does $\text{Subtotal} + \text{Tax} = \text{Total}$?
* **Salary Slips:** Does $\text{Gross Earnings} - \text{Deductions} = \text{Net Pay}$?
* **Dates:** Is the $\text{Due Date}$ on or after the $\text{Invoice Date}$?

### ⚙️ How it works (Under the hood):
* **Deterministic Python Rules:** Runs exact floating-point arithmetic checks:
  $$\text{Mismatch} = |\text{Subtotal} + \text{Tax} - \text{Total}|$$
* If the difference is greater than $\$0.05$, it logs an explicit failure in the database with the exact discrepancy (e.g., *Off by $732,000*).

---

## 📊 Station 5: The Trust Meter (Confidence Score)

### What it does:
Every single extracted field receives an objective score from **0% to 100%**. If the math failed at Station 4, the score is **instantly clamped to 50% or less**.

### ⚙️ How it works (Under the hood):
* **Linear Weighted Formula:**
  $$\text{Score} = (0.50 \times \text{OCR Clarity}) + (0.30 \times \text{Text Match}) + (0.20 \times \text{Math Pass})$$
* **Text Match:** Uses **Levenshtein String Distance** to measure how closely the extracted number matches the cited raw text.
* **The Penalty Cap:** If Math Pass is $0$, code immediately executes:
  $$\text{Final Score} = \min(\text{Calculated Score}, 0.50)$$

---

## 🕵️ Station 6: The Forensic Detective (Tamper Detection)

### What it does:
Catches fraud, forged documents, and Photoshop alterations:
1. **Digital Passport Check:** Checks if someone modified the document in Photoshop or Acrobat Pro after it was issued.
2. **Pixel X-Ray (Error Level Analysis):** Produces a color heatmap where untouched areas are dark blue and edited/pasted text glows bright light-blue/cyan.

### ⚙️ How it works (Under the hood):
* **Metadata Forensics:** Uses **PyMuPDF (`fitz`)** to inspect the PDF's internal creation timestamp, modification timestamp, and creator software string.
* **Error Level Analysis (ELA):** 
  1. Re-compresses the image in memory at **JPEG Quality 90**.
  2. Subtracts the re-compressed version from the original (`cv2.absdiff`) and amplifies the difference by **$18\times$**.
  3. Scans the page in a grid of **$64 \times 64$ pixel blocks**.
  4. If any single block has **$3\times$ higher variance** than the document's average noise floor, it flags **`HIGH RISK`** and maps it to a **JET color heatmap**.

---

## 🎯 Station 7: The Final Verdict (The Output)

### What it does:
Bundles all findings into a single response and routes the document:
1. **`AUTO ACCEPTED` (Green Light):** Score $\ge 70\%$ + math passed + no tampering $\rightarrow$ Approved immediately with zero human labor.
2. **`NEEDS REVIEW` (Yellow/Red Light):** Score $< 70\%$ OR math failed OR tampering detected $\rightarrow$ Routed to a reviewer with the problem area highlighted.

### ⚙️ How it works (Under the hood):
* **FastAPI Orchestrator:** Bundles database records (`ExtractedField`, `ValidationFlag`, `TamperFlag`) into one unified JSON response (`GET /documents/{id}/full-report`).
* **Direct Image Links:** Static image mounts allow the reviewer to view the preprocessed image and the ELA heatmap side-by-side in their browser.
