# 📄 Document Intelligence & Forensic Tamper Detection System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg?style=flat&logo=React&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.2-3178C6.svg?style=flat&logo=TypeScript&logoColor=white)](https://www.typescriptlang.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?style=flat&logo=PostgreSQL&logoColor=white)](https://www.postgresql.org)
[![PaddleOCR](https://img.shields.io/badge/PaddleOCR-GPU_Accelerated-red.svg?style=flat)](https://github.com/PaddlePaddle/PaddleOCR)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA_NIM-Nemotron--3--Ultra-76B900.svg?style=flat&logo=NVIDIA&logoColor=white)](https://build.nvidia.com)

A high-throughput, enterprise-grade Intelligent Document Processing (IDP) and forensic analysis pipeline. Built to ingest, preprocess, OCR, validate, score, and detect tampering on business documents (such as invoices and salary slips) with **zero-hallucination source citation** and **dual-layer forensic tamper detection**.

---

## 🌟 Key Capabilities

1. **GPU-Accelerated OCR & Layout Detection**:
   - Powered by PaddleOCR running on CUDA GPU (`0.80s` warm inference time vs ~40s CPU baseline — **50x speedup**).
   - Spatial grid heuristic for robust table-cell extraction, assigning `heuristic_sourced = true` for auditability.
   - Confidence gating threshold (`OCR_FLOOR_CONFIDENCE = 0.3`) routing illegible elements to `UNPROCESSABLE`.

2. **Zero-Hallucination Schema Extraction**:
   - Structured JSON schema extraction for Invoices and Salary Slips powered by LLM (NVIDIA Nemotron-3-Ultra / Claude).
   - **Mandatory Source Citation**: Every non-null extracted value must cite its exact bounding `source_element_ids`. If a field is not found in OCR elements, it returns `null` with `[]` — never an ungrounded guess.

3. **Multi-Factor Confidence Engine**:
   - Calculated mathematically, never self-reported by LLM:
     $$\text{Confidence} = 0.5 \cdot O + 0.3 \cdot S + 0.2 \cdot V$$
     Where $O$ = OCR confidence, $S$ = string similarity, $V$ = validation pass.
   - **Hard Cap**: If validation fails ($V = 0$), confidence is automatically clamped to $\le 0.50$ and flagged for human review.
   - Automated routing: $\ge 0.70 \rightarrow \text{auto\_accepted}$, $< 0.70 \rightarrow \text{needs\_review}$.

4. **Two-Tier Tamper Detection**:
   - **PDF Metadata Forensics**: Inspects `CreationDate`, `ModDate`, and `Producer`. Flags document modifications later than generation and identifies editing tools (*Photoshop, Acrobat Pro, GIMP, InDesign, Canva*). Correctly reports `NOT_APPLICABLE` for image inputs without metadata fabrication.
   - **Error Level Analysis (ELA)**: Re-compresses documents at JPEG Quality 90, computes pixel-wise absolute difference, amplifies by $18\times$, and renders human-reviewable JET color heatmaps. Analyzes $64 \times 64$ regional variance ratios to detect localized editing anomalies.

5. **Multi-Strategy Duplicate Prevention**:
   - **Byte-Level Checksum**: Instant SHA-256 duplicate detection during ingestion.
   - **Semantic Duplication**: Detects identical invoice numbers across different file uploads.

6. **Unified Full-Report API**:
   - One endpoint (`GET /api/v1/documents/{id}/full-report`) returns extracted fields, source element citations, line items, math validation flags, tamper analysis, and duplication status in a single payload.

---

## 🏛️ System Architecture

```
                    ┌────────────────────────┐
                    │ Raw Document Ingestion │
                    │   (PDF / JPG / PNG)    │
                    └───────────┬────────────┘
                                │
                 SHA-256 Check & Preprocessing
            (Deskew, Grayscale, Denoise, Threshold)
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │       GPU PaddleOCR & Layout Analysis        │
         │  - Text Boxes (det + rec)                    │
         │  - Spatial Grid Table Heuristic              │
         │  - Low Confidence Filter (conf < 0.3)        │
         └──────────────────────┬───────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │       LLM Schema Extraction & Citation       │
         │  - Strict JSON Schema Mapping                │
         │  - Mandatory source_element_ids Citation     │
         └──────────────────────┬───────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │           Deterministic Validation           │
         │  - Math: Subtotal + Tax == Total             │
         │  - Math: Gross - Deductions == Net Pay       │
         │  - Dates: Due Date >= Invoice Date           │
         └──────────────────────┬───────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │            Confidence Engine                 │
         │  - 0.5*OCR + 0.3*Similarity + 0.2*Validation │
         │  - V=0 Clamping (<= 0.50)                    │
         └──────────────────────┬───────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │          Forensic Tamper Detection           │
         │  - PDF Metadata (Creation vs Mod, Producer)  │
         │  - ELA (JPEG Q=90 Delta, 18x JET Heatmap)    │
         └──────────────────────┬───────────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │          Unified Report & Human UI           │
         │  - GET /documents/{id}/full-report           │
         │  - Interactive Review & Bounding Box View    │
         └──────────────────────────────────────────────┘
```

---

## 📁 Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py         # REST endpoints (upload, pipeline, full-report, ocr)
│   │   ├── confidence/
│   │   │   └── engine.py         # 0.5*O + 0.3*S + 0.2*V confidence formula calculator
│   │   ├── core/
│   │   │   └── config.py         # Application configuration & Pydantic settings
│   │   ├── db/
│   │   │   ├── models.py         # SQLAlchemy ORM models (documents, ocr, fields, flags)
│   │   │   └── session.py        # Database session engine & connection pooling
│   │   ├── llm/
│   │   │   └── extractor.py      # Zero-hallucination extraction with source citation
│   │   ├── ocr/
│   │   │   └── engine.py         # GPU PaddleOCR engine & spatial table grid heuristic
│   │   ├── preprocessing/
│   │   │   └── pipeline.py       # PDF conversion, deskewing, and image enhancement
│   │   ├── tamper/
│   │   │   └── detector.py       # PDF metadata forensics & Error Level Analysis (ELA)
│   │   ├── validation/
│   │   │   └── rules.py          # Arithmetic & date consistency validation rules
│   │   ├── main.py               # FastAPI application setup & static storage mounts
│   │   └── pipeline.py           # End-to-end processing orchestrator
│   ├── requirements.txt          # Python dependencies
│   └── test_db.py                # Database connection check
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ConfidenceBadge.tsx  # Confidence breakdown pill (O, S, V)
│   │   │   ├── DocumentViewer.tsx   # Interactive image canvas with bounding boxes
│   │   │   └── Layout.tsx           # Application navigation shell
│   │   ├── App.tsx                  # Main application router and state
│   │   └── index.css                # Custom UI styling and tokens
│   ├── package.json
│   └── vite.config.ts
├── storage/                      # Image & heatmap storage
│   ├── raw/                      # Original uploaded documents
│   ├── preprocessed/             # Deskewed & cleaned images
│   └── tamper/                   # Generated ELA color heatmaps
├── docker-compose.yml            # PostgreSQL 16 container definition
└── full_pipeline_reports.json    # Verification reports on test documents
```

---

## 🚀 Quickstart Guide

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- Docker Desktop (for PostgreSQL 16)
- *(Optional for GPU acceleration)*: NVIDIA Driver & CUDA 12+

### 1. Database Setup
Start the PostgreSQL 16 container:
```bash
docker compose up -d
```
The database will be accessible on `localhost:5433` (DB: `doc_intelligence`, User: `postgres`, Password: `postgrespassword`).

### 2. Backend Setup
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate       # Windows
# source venv/bin/activate    # Linux / macOS

# Install dependencies
pip install -r requirements.txt

# (Optional: For NVIDIA GPU acceleration)
# pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/nightly/cuda123/

# Configure environment variables
cp .env.example .env
# Edit .env with your LLM API Key (NVIDIA NIM or OpenAI-compatible)

# Start FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Swagger UI will be live at: **[http://localhost:8000/docs](http://localhost:8000/docs)**

### 3. Frontend Setup
```bash
cd frontend

npm install
npm run dev
```
The web dashboard will be accessible at: **[http://localhost:5173](http://localhost:5173)**

---

## 📡 REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/documents/upload` | Ingests document, checks SHA-256 duplicate, and deskews/preprocesses. |
| `POST` | `/api/v1/documents/{id}/process` | Runs GPU PaddleOCR and spatial table layout heuristic. |
| `POST` | `/api/v1/documents/{id}/extract` | Executes LLM schema extraction with source citation. |
| `POST` | `/api/v1/documents/{id}/pipeline` | Runs the entire pipeline end-to-end synchronously. |
| `GET` | `/api/v1/documents/{id}/full-report` | Retrieves all fields, confidence scores, validation flags, and tamper analysis. |
| `GET` | `/api/v1/documents/{id}/ocr` | Returns all raw OCR text boxes, confidence, and table cells. |
| `GET` | `/api/v1/documents/{id}/fields` | Returns extracted scalar fields and line items. |
| `GET` | `/storage/tamper/{file}` | Serves visual ELA color heatmaps directly for visual inspection. |

---

## 🧪 Verification Walkthrough

To independently verify the pipeline without relying on test stubs:

1. **Upload Document**:
   Use Swagger UI to call `POST /api/v1/documents/upload`. Re-upload the exact same file to verify that `is_duplicate: true` is immediately detected via SHA-256.
2. **Execute Full Pipeline**:
   Call `POST /api/v1/documents/{id}/pipeline`.
3. **Inspect Output**:
   Call `GET /api/v1/documents/{id}/full-report`.
   - **Citation Check**: Confirm every non-null field has non-empty `source_element_ids` matching the OCR text.
   - **Math Verification**: Compute $0.5 \cdot O + 0.3 \cdot S + 0.2 \cdot V$ by hand and verify it matches `confidence`.
   - **Tamper Inspection**: Open the returned `heatmap_url` in your browser (e.g. `http://localhost:8000/storage/tamper/{id}_ela_heatmap.png`) to inspect compression noise distribution.

---

## 🛡️ License

This project is licensed under the MIT License.
