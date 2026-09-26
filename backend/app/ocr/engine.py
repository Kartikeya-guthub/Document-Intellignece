import cv2
import numpy as np
from typing import List, Dict
import logging
import os as _os

_os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

logger = logging.getLogger(__name__)

_engine_instance = None

def _get_structure():
    global _engine_instance
    if _engine_instance is None:
        import paddle
        from paddleocr import PPStructureV3
        device = "gpu:0" if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0 else "cpu"
        if device.startswith("gpu"):
            paddle.set_device(device)
        logger.info(f"Initializing PPStructureV3 on {device}...")
        _engine_instance = PPStructureV3(
            device=device,
            layout_detection_model_name='PP-DocBlockLayout',
            use_table_recognition=False,
            use_seal_recognition=False,
            use_formula_recognition=False,
            use_chart_recognition=False,
            use_doc_unwarping=False,
            use_doc_orientation_classify=False,
            lang='en'
        )
        logger.info(f"PPStructureV3 ready on {device}.")
    return _engine_instance

def calculate_intersection_ratio(text_box_xywh, region_box):
    # text_box is [x, y, w, h]; region_box from PaddleX is [x1, y1, x2, y2]
    tx1 = text_box_xywh[0]
    ty1 = text_box_xywh[1]
    tx2 = text_box_xywh[0] + text_box_xywh[2]
    ty2 = text_box_xywh[1] + text_box_xywh[3]
    x_left = max(tx1, region_box[0])
    y_top = max(ty1, region_box[1])
    x_right = min(tx2, region_box[2])
    y_bottom = min(ty2, region_box[3])
    if x_right < x_left or y_bottom < y_top: return 0.0
    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    text_area = text_box_xywh[2] * text_box_xywh[3]
    return intersection_area / float(text_area + 1e-6)

def infer_table_grid(elements: List[Dict]) -> List[Dict]:
    for el in elements:
        box = eval(el['bbox'])  # [x, y, w, h]
        el['_cx'] = box[0] + box[2] / 2
        el['_cy'] = box[1] + box[3] / 2
    elements.sort(key=lambda x: x['_cy'])
    rows = []
    current_row = []
    y_tolerance = 15
    for el in elements:
        if not current_row:
            current_row.append(el)
        else:
            if abs(el['_cy'] - current_row[0]['_cy']) <= y_tolerance:
                current_row.append(el)
            else:
                rows.append(current_row)
                current_row = [el]
    if current_row:
        rows.append(current_row)
    table_rows = [r for r in rows if len(r) > 1]
    if len(table_rows) >= 2:
        for r_idx, row in enumerate(table_rows):
            row.sort(key=lambda x: x['_cx'])
            for c_idx, el in enumerate(row):
                el['region_type'] = 'table_cell'
                el['table_row'] = r_idx
                el['table_col'] = c_idx
    for el in elements:
        el.pop('_cx', None)
        el.pop('_cy', None)
    return elements

def run_ocr_and_layout(img: np.ndarray, doc_id) -> List[Dict]:
    engine = _get_structure()
    try:
        results = list(engine.predict(img))
    except Exception as e:
        logger.error(f"Engine prediction failed: {e}")
        return []
    if not results: return []
    res = results[0]
    regions = []
    layout_res = res.get('layout_det_res', {})
    if layout_res and 'boxes' in layout_res:
        for box in layout_res['boxes']:
            regions.append({
                'label': box.get('label', 'paragraph'),
                'score': box.get('score', 0.0),
                'bbox': box.get('coordinate', [0,0,0,0])
            })
    is_layout_failed = len(regions) == 0
    elements = []
    ocr_res = res.get('overall_ocr_res', {})
    if not ocr_res: return elements
    texts = ocr_res.get('rec_texts', ocr_res.get('rec_text', []))
    scores = ocr_res.get('rec_scores', [])
    boxes = ocr_res.get('dt_polys', ocr_res.get('rec_boxes', []))
    for idx, (text, score, box) in enumerate(zip(texts, scores, boxes)):
        if not text.strip(): continue
        if isinstance(box, (list, np.ndarray)) and len(box) == 4 and isinstance(box[0], (list, np.ndarray)):
            pts = np.array(box)
            x1, y1, x2, y2 = float(np.min(pts[:,0])), float(np.min(pts[:,1])), float(np.max(pts[:,0])), float(np.max(pts[:,1]))
        else:
            arr = [float(x) for x in box]
            x1, y1, x2, y2 = arr[0], arr[1], arr[2], arr[3]
        # Convert to [x, y, w, h] - Phase 1 locked contract format
        bbox = [x1, y1, x2 - x1, y2 - y1]
        best_region_label = 'paragraph'
        best_region_score = 0.0
        best_intersection = 0.0
        for region in regions:
            ratio = calculate_intersection_ratio(bbox, region['bbox'])
            if ratio > best_intersection and ratio > 0.5:
                best_intersection = ratio
                best_region_label = region['label']
                best_region_score = region['score']
        region_status = 'PROCESSED'
        if score < 0.3 or is_layout_failed:
            region_status = 'UNPROCESSABLE'
        elements.append({
            "document_id": doc_id,
            "page_number": 1,
            "text": text,
            "bbox": str(bbox),
            "confidence": float(score),
            "region_type": best_region_label,
            "region_confidence": float(best_region_score),
            "region_status": region_status,
            "table_row": None,
            "table_col": None
        })
    elements = infer_table_grid(elements)
    return elements
