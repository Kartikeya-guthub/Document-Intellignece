import React from 'react';

interface ConfidenceBadgeProps {
  confidence: number;
  ocrConfidence: number;
  stringSimilarity: number;
  validationPass: number;
}

/**
 * Renders the locked confidence breakdown:
 * confidence = 0.5*O + 0.3*S + 0.2*V
 * Highlights in red/amber if confidence < 0.7 or validation failed.
 */
export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  ocrConfidence,
  stringSimilarity,
  validationPass
}) => {
  const needsReview = confidence < 0.7 || validationPass === 0;

  return (
    <div
      className={`px-2 py-1 rounded text-xs font-mono inline-flex items-center gap-1 ${
        needsReview
          ? 'bg-amber-100 text-amber-800 border border-amber-300'
          : 'bg-green-100 text-green-800 border border-green-300'
      }`}
    >
      <span>{(confidence * 100).toFixed(1)}%</span>
      <span className="text-[10px] opacity-75">
        (O: {ocrConfidence.toFixed(2)} | S: {stringSimilarity.toFixed(2)} | V: {validationPass})
      </span>
    </div>
  );
};
