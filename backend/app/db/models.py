import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.session import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    preprocessed_path = Column(Text, nullable=True)
    doc_type = Column(String(50), nullable=True) # 'invoice' | 'salary_slip'
    status = Column(String(50), default="uploaded", nullable=False) 
    # Statuses: 'uploaded', 'preprocessed', 'ocr_completed', 'extracted', 'needs_review', 'approved'
    doc_metadata = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    extracted_fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")
    validation_flags = relationship("ValidationFlag", back_populates="document", cascade="all, delete-orphan")
    corrections_log = relationship("CorrectionLog", back_populates="document", cascade="all, delete-orphan")
    ocr_elements = relationship("OcrElement", back_populates="document", cascade="all, delete-orphan")
    tamper_flags = relationship("TamperFlag", back_populates="document", cascade="all, delete-orphan")


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    extracted_value = Column(Text, nullable=True)
    source_span_id = Column(Integer, nullable=True)
    raw_ocr_text = Column(Text, nullable=True)
    
    # Phase 4 Citation
    source_element_ids = Column(JSONB, default=list, nullable=True) # List of OcrElement UUIDs
    line_item_group_id = Column(String(100), nullable=True) # For line_item groupings
    extracted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Confidence Formula Inputs (0.0 to 1.0) - Phase 5
    ocr_confidence = Column(Float, nullable=True) # O
    string_similarity = Column(Float, nullable=True) # S
    validation_pass = Column(Integer, default=1, nullable=False) # V (0 or 1)
    final_confidence = Column(Float, nullable=True) # Calculated score
    
    # Spatial & Layout Evidence
    bbox = Column(JSONB, nullable=True) # [x, y, w, h]
    region_type = Column(String(50), nullable=True) # 'table_cell' | 'paragraph' | 'title' | 'figure'
    row = Column(Integer, nullable=True)
    col = Column(Integer, nullable=True)
    page = Column(Integer, default=1, nullable=False)
    
    # Review Workflow
    review_status = Column(String(50), default="needs_review", nullable=False) # 'auto_accepted' | 'needs_review' | 'corrected' | 'rejected'
    is_unprocessable = Column(Boolean, default=False, nullable=False) # Marked by OCR failure gate

    document = relationship("Document", back_populates="extracted_fields")


class ValidationFlag(Base):
    __tablename__ = "validation_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    rule_name = Column(String(100), nullable=False) # e.g. 'subtotal_tax_sum', 'due_after_invoice'
    passed = Column(Boolean, nullable=False)
    details = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="validation_flags")


class CorrectionLog(Base):
    __tablename__ = "corrections_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(100), nullable=False)
    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=False)
    original_bbox = Column(JSONB, nullable=True)
    corrected_bbox = Column(JSONB, nullable=True)
    reviewer_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="corrections_log")


class OcrElement(Base):
    """
    Phase 3 - Persisted OCR extraction unit.
    Every text element detected by PaddleOCR is stored here before LLM structuring.
    Shape mirrors the locked Phase 1 OCR-to-LLM JSON contract exactly.
    """
    __tablename__ = "ocr_elements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Locked contract fields (do NOT rename without Phase 1 approval) ---
    text              = Column(Text, nullable=False)
    bbox              = Column(JSONB, nullable=False)          # [x, y, w, h]
    conf              = Column(Float, nullable=False)
    region_type       = Column(String(50), nullable=False)     # table_cell | paragraph | title | figure
    row               = Column(Integer, nullable=True)         # null unless region_type == table_cell
    col               = Column(Integer, nullable=True)         # null unless region_type == table_cell
    page              = Column(Integer, default=1, nullable=False)
    region_status     = Column(String(20), default="OK", nullable=False)  # OK | UNPROCESSABLE
    heuristic_sourced = Column(Boolean, default=False, nullable=False)     # Phase 4: True if spatial grid heuristic used

    created_at        = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="ocr_elements")


class TamperFlag(Base):
    """
    Tamper Detection Integration.
    Stores forensic metadata analysis and Error Level Analysis (ELA) signals.
    """
    __tablename__ = "tamper_flags"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    document_id  = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_type   = Column(String(50), nullable=False)  # 'metadata' | 'ela'
    result       = Column(String(50), nullable=False)  # 'SUSPICIOUS' | 'CLEAN' | 'NOT_APPLICABLE'
    risk_level   = Column(String(20), nullable=False)  # 'HIGH' | 'MEDIUM' | 'LOW' | 'N/A'
    details      = Column(JSONB, default=dict, nullable=False)
    heatmap_path = Column(Text, nullable=True)         # For ELA
    created_at   = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("Document", back_populates="tamper_flags")
