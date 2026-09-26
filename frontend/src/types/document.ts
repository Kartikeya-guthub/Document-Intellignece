export type RegionType = 'table_cell' | 'paragraph' | 'title' | 'figure';

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ExtractedField {
  id: string;
  document_id: string;
  field_name: string;
  extracted_value: string | null;
  source_span_id: number | null;
  raw_ocr_text: string | null;
  ocr_confidence: number; // O (0-1)
  string_similarity: number; // S (0-1)
  validation_pass: number; // V (0 or 1)
  final_confidence: number; // 0.5*O + 0.3*S + 0.2*V (capped at 0.5 if V=0)
  bbox: [number, number, number, number] | null;
  region_type: RegionType | null;
  row: number | null;
  col: number | null;
  page: number;
  review_status: 'auto_accepted' | 'needs_review' | 'corrected' | 'rejected';
  is_unprocessable: boolean;
}

export interface DocumentReviewState {
  id: string;
  filename: string;
  preprocessed_image_url: string;
  doc_type: 'invoice' | 'salary_slip' | null;
  status: string;
  fields: ExtractedField[];
}
