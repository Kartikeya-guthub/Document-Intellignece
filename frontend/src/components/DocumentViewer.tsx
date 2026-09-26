import React from 'react';
import type { ExtractedField } from '../types/document';

export interface DocumentViewerProps {
  imageUrl?: string;
  fields?: ExtractedField[];
  selectedFieldId?: string;
  onSelectField?: (fieldId: string) => void;
}

/**
 * STUB: Reviewer Document Viewer with Canvas/SVG BBox Overlay.
 * 
 * Rules:
 * - Displays the PREPROCESSED image (post-deskew/crop), not the raw upload.
 * - Renders interactive bounding boxes linked to field review status.
 */
export const DocumentViewer: React.FC<DocumentViewerProps> = () => {
  return (
    <div className="relative border rounded bg-slate-900 flex items-center justify-center min-h-[500px]">
      <div className="text-slate-400 text-sm">
        [DocumentViewer Stub: Preprocessed Image + SVG/Canvas BBox Overlay will be wired in Phase 6+]
      </div>
    </div>
  );
};
