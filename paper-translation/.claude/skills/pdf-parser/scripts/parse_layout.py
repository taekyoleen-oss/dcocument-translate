#!/usr/bin/env python3
"""
parse_layout.py
PDF 레이아웃을 분석해 각 요소(텍스트, 수식, 코드, 표, 이미지)를 분류한다.

출력: <output>/layout_map.json
  [{page, elements: [{type, bbox, content_ref, column, text?, cells?}]}]
"""

import argparse
import json
import os
import re
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF(fitz) not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)

# LaTeX 수식 패턴
INLINE_FORMULA_PATTERNS = re.compile(
    r"(\$[^$\n]+\$)"
    r"|(\\\(.*?\\\))"
    r"|(\\alpha|\\beta|\\gamma|\\delta|\\epsilon|\\theta|\\lambda|\\mu|\\pi|\\sigma|\\omega)"
    r"|(\\frac\{|\\int_|\\sum_|\\prod_|\\nabla|\\partial)"
)

# 섹션 헤더 패턴
SECTION_HEADER_PATTERN = re.compile(
    r"^(\d+\.?\s+[A-Z]|[IVX]+\.\s+[A-Z]|[A-Z][A-Z ]{3,}$)"
)

MONO_FONTS = {"courier", "couriernew", "lucidaconsole", "consolas", "monospace", "dejavumono"}


def detect_columns(page: fitz.Page) -> int:
    """페이지가 1단인지 2단 컬럼인지 판별한다."""
    page_width = page.rect.width
    blocks = page.get_text("blocks")

    left_blocks = [b for b in blocks if (b[0] + b[2]) / 2 < page_width * 0.5]
    right_blocks = [b for b in blocks if (b[0] + b[2]) / 2 >= page_width * 0.5]

    if len(left_blocks) >= 3 and len(right_blocks) >= 3:
        return 2
    return 1


def is_code_block(block: tuple, page: fitz.Page) -> bool:
    """
    블록이 코드 블록인지 판별한다.
    기준: Courier/Mono 계열 폰트 + 좌측 들여쓰기 또는 균일 간격.
    """
    x0, y0, x1, y1 = block[:4]
    page_width = page.rect.width

    # bbox 폭 비율: 코드 블록은 보통 페이지 너비의 30-90% 범위
    width_ratio = (x1 - x0) / page_width if page_width > 0 else 0
    if width_ratio < 0.2 or width_ratio > 0.95:
        return False

    # 폰트 정보 추출
    dict_data = page.get_text("dict", clip=fitz.Rect(x0, y0, x1, y1))
    for blk in dict_data.get("blocks", []):
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                font_name = span.get("font", "").lower()
                if any(mono in font_name for mono in MONO_FONTS):
                    return True
    return False


def is_formula_inline(text: str) -> bool:
    """텍스트에 인라인 수식 패턴이 포함되어 있는지 확인한다."""
    return bool(INLINE_FORMULA_PATTERNS.search(text))


def classify_element(block: tuple, page: fitz.Page, n_cols: int) -> dict:
    """
    블록을 요소 유형으로 분류한다.
    반환: {type, bbox, column, text?, content_ref?}
    """
    x0, y0, x1, y1, text, block_no, block_type = block[:7]
    bbox = [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]
    column = assign_column(bbox, page.rect.width, n_cols)

    # 이미지 블록
    if block_type == 1:
        return {
            "type": "asset",
            "bbox": bbox,
            "column": column,
            "content_ref": f"fig_p{page.number + 1}_{block_no}",
        }

    text = text.strip()

    # 빈 블록 스킵 표시
    if not text:
        return None

    # 수식 블록 ($$...$$, \[...\] 패턴으로 시작하는 블록)
    if text.startswith("$$") or text.startswith("\\["):
        return {
            "type": "formula_block",
            "bbox": bbox,
            "column": column,
            "content_ref": f"formula_p{page.number + 1}_{block_no}",
            "text": text,
        }

    # 코드 블록
    if is_code_block(block, page):
        return {
            "type": "code",
            "bbox": bbox,
            "column": column,
            "content_ref": f"code_p{page.number + 1}_{block_no}",
            "text": text,
        }

    # 섹션 헤더
    first_line = text.split("\n")[0].strip()
    if SECTION_HEADER_PATTERN.match(first_line):
        return {
            "type": "section_header",
            "bbox": bbox,
            "column": column,
            "text": text,
        }

    # 캡션 (Figure / Table / Fig. 로 시작)
    if re.match(r"^(Figure|Fig\.|Table|그림|표)\s*\d+", first_line, re.IGNORECASE):
        return {
            "type": "caption",
            "bbox": bbox,
            "column": column,
            "text": text,
        }

    # 인라인 수식 포함 텍스트
    if is_formula_inline(text):
        return {
            "type": "formula_inline",
            "bbox": bbox,
            "column": column,
            "text": text,
        }

    # 일반 텍스트
    return {
        "type": "text",
        "bbox": bbox,
        "column": column,
        "text": text,
    }


def assign_column(bbox: list, page_width: float, n_cols: int) -> int:
    """
    요소가 속하는 컬럼을 반환한다.
    단단(1): 0, 2단(2): 좌=1, 우=2
    """
    if n_cols == 1:
        return 0
    cx = (bbox[0] + bbox[2]) / 2
    return 1 if cx < page_width / 2 else 2


def extract_table_cells(plumber_page, bbox: list):
    """
    pdfplumber로 지정 bbox 내 표 셀을 추출한다.
    반환: [[row, col, text], ...] 또는 None
    """
    try:
        cropped = plumber_page.within_bbox(tuple(bbox))
        tables = cropped.extract_tables()
        if not tables:
            return None
        cells = []
        for table in tables:
            for r_idx, row in enumerate(table):
                for c_idx, cell in enumerate(row):
                    cells.append([r_idx, c_idx, cell or ""])
        return cells if cells else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="PDF 레이아웃 파싱")
    parser.add_argument("--pdf", required=True, help="입력 PDF 파일 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"ERROR: PDF 파일을 찾을 수 없음: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    doc = fitz.open(args.pdf)
    plumber_doc = pdfplumber.open(args.pdf)
    layout_map = []

    for page_idx, page in enumerate(doc):
        plumber_page = plumber_doc.pages[page_idx]
        n_cols = detect_columns(page)
        blocks = page.get_text("blocks")
        elements = []

        for block in blocks:
            elem = classify_element(block, page, n_cols)
            if elem is None:
                continue

            # 표 감지: 요소 bbox로 pdfplumber 표 추출 시도
            if elem["type"] == "text":
                cells = extract_table_cells(plumber_page, elem["bbox"])
                if cells:
                    elem["type"] = "table"
                    elem["cells"] = cells
                    elem.pop("text", None)

            elements.append(elem)

        layout_map.append({
            "page": page_idx + 1,
            "n_cols": n_cols,
            "elements": elements,
        })

    doc.close()
    plumber_doc.close()

    output_path = os.path.join(args.output, "layout_map.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(layout_map, f, ensure_ascii=False, indent=2)

    total_elements = sum(len(p["elements"]) for p in layout_map)
    print(f"layout_map.json 저장 완료: {output_path}")
    print(f"  총 {len(layout_map)} 페이지, {total_elements}개 요소")


if __name__ == "__main__":
    main()
