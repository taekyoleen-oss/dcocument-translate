#!/usr/bin/env python3
"""
compose_pdf.py
번역 결과와 에셋을 합쳐 한국어 PDF를 생성한다.

출력:
  <output>/translated_draft.pdf
  <output>/overflow_log.json (오버플로우 발생 시)
폰트: --font 인자 또는 fonts/NanumGothic.ttf (기본값)
"""

import argparse
import json
import os
import sys
from typing import Optional

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import pt
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as rl_canvas
except ImportError:
    print("ERROR: reportlab not installed. Run: pip install reportlab", file=sys.stderr)
    sys.exit(1)

try:
    import fitz  # PyMuPDF - 원본 페이지 크기 참조용
except ImportError:
    print("ERROR: PyMuPDF(fitz) not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image as PILImage
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(1)

FONT_SIZES = [11, 8, 6]  # 오버플로우 시 순차 축소


def load_font(font_path: str, font_name: str = "NanumGothic") -> str:
    """
    TTF 폰트를 reportlab에 등록하고 폰트 이름을 반환한다.
    폰트 파일이 없으면 Helvetica 폴백.
    """
    if os.path.isfile(font_path):
        try:
            pdfmetrics.registerFont(TTFont(font_name, font_path))
            print(f"  폰트 등록: {font_name} ({font_path})")
            return font_name
        except Exception as e:
            print(f"  WARNING: 폰트 등록 실패 ({e}), Helvetica 사용", file=sys.stderr)
    else:
        print(f"  WARNING: 폰트 파일 없음: {font_path}, Helvetica 사용", file=sys.stderr)
    return "Helvetica"


def fit_text_in_bbox(
    text: str, bbox: list, c: rl_canvas.Canvas, font_name: str, initial_size: int = 11
) -> tuple:
    """
    텍스트를 bbox에 맞는 폰트 크기로 조정한다.
    반환: (text_to_place, font_size, truncated: bool)
    """
    x0, y0, x1, y1 = bbox
    box_width = x1 - x0
    box_height = y1 - y0

    for font_size in FONT_SIZES:
        if font_size > initial_size:
            continue
        c.setFont(font_name, font_size)
        # 간단한 텍스트 폭 추정
        lines = text.split("\n")
        max_line_width = max(c.stringWidth(line, font_name, font_size) for line in lines) if lines else 0
        total_height = len(lines) * font_size * 1.2  # 줄 간격 1.2

        if max_line_width <= box_width and total_height <= box_height:
            return text, font_size, False

    # 모든 크기에서 오버플로우 → 잘라내기
    font_size = FONT_SIZES[-1]
    c.setFont(font_name, font_size)
    max_chars_per_line = max(1, int(box_width / (font_size * 0.6)))
    max_lines = max(1, int(box_height / (font_size * 1.2)))

    truncated_lines = []
    for line in text.split("\n")[:max_lines]:
        truncated_lines.append(line[:max_chars_per_line])

    return "\n".join(truncated_lines), font_size, True


def place_text(
    c: rl_canvas.Canvas,
    text: str,
    bbox: list,
    font_name: str,
    font_size: float,
    page_height: float,
) -> None:
    """bbox 내에 텍스트를 배치한다. reportlab 좌표계(y 역방향) 변환 포함."""
    x0, y0, x1, y1 = bbox
    # PDF 좌표: y0는 위쪽, reportlab: y는 아래쪽 기준
    rl_y = page_height - y0 - font_size

    c.setFont(font_name, font_size)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        c.drawString(x0, rl_y - i * font_size * 1.2, line)


def place_asset(c: rl_canvas.Canvas, filepath: str, bbox: list, page_height: float) -> None:
    """bbox 위치에 이미지를 배치한다."""
    if not os.path.isfile(filepath):
        print(f"  WARNING: 에셋 파일 없음: {filepath}", file=sys.stderr)
        return
    x0, y0, x1, y1 = bbox
    w = x1 - x0
    h = y1 - y0
    rl_y = page_height - y1  # reportlab y 변환
    c.drawImage(filepath, x0, rl_y, width=w, height=h, preserveAspectRatio=True, mask="auto")


def render_table(
    c: rl_canvas.Canvas,
    cells: list,
    bbox: list,
    font_name: str,
    font_size: float,
    page_height: float,
) -> None:
    """간단한 표를 bbox 내에 렌더링한다."""
    x0, y0, x1, y1 = bbox
    if not cells:
        return

    rows = max(cell[0] for cell in cells) + 1
    cols = max(cell[1] for cell in cells) + 1
    cell_w = (x1 - x0) / max(cols, 1)
    cell_h = (y1 - y0) / max(rows, 1)

    c.setFont(font_name, font_size)
    c.setLineWidth(0.5)

    for cell in cells:
        row, col, text = cell[0], cell[1], str(cell[2]) if cell[2] else ""
        cx = x0 + col * cell_w
        cy_top = y0 + row * cell_h
        rl_cy = page_height - cy_top - font_size - 2

        # 셀 테두리
        c.rect(cx, page_height - cy_top - cell_h, cell_w, cell_h)
        # 셀 텍스트 (넘치면 잘라냄)
        max_chars = max(1, int(cell_w / (font_size * 0.6)))
        c.drawString(cx + 2, rl_cy, text[:max_chars])


def render_formula_inline(
    c: rl_canvas.Canvas,
    text: str,
    bbox: list,
    font_name: str,
    font_size: float,
    page_height: float,
) -> None:
    """인라인 수식을 원문 그대로 배치한다 (번역 없음)."""
    place_text(c, text, bbox, font_name, font_size, page_height)


def log_overflow(
    overflow_log: list,
    page: int,
    bbox: list,
    truncated_text: str,
    original_text: str,
) -> None:
    """오버플로우 정보를 로그 리스트에 추가한다."""
    overflow_log.append({
        "page": page,
        "bbox": bbox,
        "truncated_at": len(truncated_text),
        "original_length": len(original_text),
        "preview": original_text[:100],
    })


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_font = os.path.join(script_dir, "..", "..", "..", "fonts", "NanumGothic.ttf")
    default_font = os.path.normpath(default_font)

    parser = argparse.ArgumentParser(description="번역 PDF 조합")
    parser.add_argument("--layout", required=True, help="layout_map.json 경로")
    parser.add_argument("--translation", required=True, help="translation_final.json 경로")
    parser.add_argument("--assets", required=True, help="에셋 디렉터리 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    parser.add_argument("--font", default=default_font, help="한글 TTF 폰트 경로")
    args = parser.parse_args()

    for path, name in [(args.layout, "layout_map.json"), (args.translation, "translation_final.json")]:
        if not os.path.isfile(path):
            print(f"ERROR: {name}을 찾을 수 없음: {path}", file=sys.stderr)
            sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    with open(args.layout, "r", encoding="utf-8") as f:
        layout_map = json.load(f)
    with open(args.translation, "r", encoding="utf-8") as f:
        translations = json.load(f)

    # 번역 데이터를 (page, bbox) 키로 인덱싱
    trans_index = {}
    for chunk in translations:
        for elem in chunk.get("translated_elements", []):
            key = (elem.get("page"), tuple(elem.get("bbox", [])))
            trans_index[key] = elem

    # 에셋 매니페스트 로드
    manifest_path = os.path.join(args.assets, "..", "assets_manifest.json")
    manifest_path = os.path.normpath(manifest_path)
    assets_index = {}
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for item in manifest:
            key = (item["page"], tuple(item["bbox"]))
            assets_index[key] = item["filepath"]

    font_name = load_font(args.font)
    output_pdf = os.path.join(args.output, "translated_draft.pdf")
    overflow_log = []

    # 첫 페이지로 페이지 크기 결정
    if layout_map:
        page_width_pt, page_height_pt = A4  # 기본 A4
    c = rl_canvas.Canvas(output_pdf, pagesize=(page_width_pt, page_height_pt))

    for page_data in layout_map:
        page_num = page_data["page"]
        elements = page_data["elements"]

        for elem in elements:
            elem_type = elem.get("type")
            bbox = elem.get("bbox", [])
            if not bbox or len(bbox) < 4:
                continue

            bbox_key = (page_num, tuple(bbox))

            if elem_type in ("text", "section_header", "caption"):
                trans = trans_index.get(bbox_key)
                text = trans.get("translated", elem.get("text", "")) if trans else elem.get("text", "")
                if not text:
                    continue
                fitted_text, font_size, truncated = fit_text_in_bbox(text, bbox, c, font_name)
                place_text(c, fitted_text, bbox, font_name, font_size, page_height_pt)
                if truncated:
                    log_overflow(overflow_log, page_num, bbox, fitted_text, text)

            elif elem_type == "table":
                trans = trans_index.get(bbox_key)
                cells = trans.get("translated_cells", elem.get("cells", [])) if trans else elem.get("cells", [])
                render_table(c, cells, bbox, font_name, 9, page_height_pt)

            elif elem_type == "formula_inline":
                text = elem.get("text", "")
                render_formula_inline(c, text, bbox, font_name, 10, page_height_pt)

            elif elem_type in ("formula_block", "code", "asset"):
                filepath = assets_index.get(bbox_key)
                if filepath:
                    place_asset(c, filepath, bbox, page_height_pt)

        c.showPage()

    c.save()
    print(f"번역 PDF 저장 완료: {output_pdf}")

    if overflow_log:
        overflow_path = os.path.join(args.output, "overflow_log.json")
        with open(overflow_path, "w", encoding="utf-8") as f:
            json.dump(overflow_log, f, ensure_ascii=False, indent=2)
        print(f"오버플로우 로그 ({len(overflow_log)}건): {overflow_path}")


if __name__ == "__main__":
    main()
