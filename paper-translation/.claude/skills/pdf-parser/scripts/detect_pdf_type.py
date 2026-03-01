#!/usr/bin/env python3
"""
detect_pdf_type.py
PDF 파일의 유형(digital/scanned), 레이아웃, 도메인 등 메타데이터를 감지한다.

출력: <output>/pdf_meta.json
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


SUPPORTED_DOMAINS = {"cs", "physics", "chemistry", "medicine", "biology", "economics"}

FORMULA_PATTERNS = [
    r"\$[^$]+\$",          # inline LaTeX
    r"\$\$[^$]+\$\$",      # display LaTeX
    r"\\frac\{",
    r"\\sum_",
    r"\\int_",
    r"\\alpha|\\beta|\\gamma|\\delta|\\epsilon",
    r"\\partial",
    r"\\nabla",
]


def parse_domain(filename: str) -> str:
    """
    파일명에서 도메인을 파싱한다.
    형식: {domain}_{filename}.pdf
    인식 불가 시 'unknown' 반환.
    """
    basename = os.path.basename(filename)
    name_no_ext = os.path.splitext(basename)[0]
    parts = name_no_ext.split("_", 1)
    if parts and parts[0].lower() in SUPPORTED_DOMAINS:
        return parts[0].lower()
    return "unknown"


def detect_type(pdf_path: str) -> str:
    """
    PDF가 디지털 텍스트 기반인지 스캔본인지 판별한다.
    텍스트가 거의 없으면 'scanned', 아니면 'digital'.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    text_pages = 0

    for page in doc:
        text = page.get_text("text").strip()
        if len(text) > 50:  # 의미 있는 텍스트가 있는 페이지
            text_pages += 1

    doc.close()

    if total_pages == 0:
        return "digital"

    text_ratio = text_pages / total_pages
    return "digital" if text_ratio >= 0.5 else "scanned"


def detect_layout_type(doc: fitz.Document) -> str:
    """
    페이지 레이아웃이 단단(single) 혹은 2단(double_column)인지 추정한다.
    텍스트 블록의 x 좌표 분포를 분석해 판별.
    """
    page_width_sum = 0.0
    double_col_votes = 0
    sample_pages = min(5, len(doc))

    for i in range(sample_pages):
        page = doc[i]
        page_width = page.rect.width
        page_width_sum += page_width
        blocks = page.get_text("blocks")

        # 블록 중심 x 좌표 수집
        centers = []
        for b in blocks:
            x0, y0, x1, y1, *_ = b
            centers.append((x0 + x1) / 2)

        if not centers:
            continue

        left_count = sum(1 for c in centers if c < page_width * 0.5)
        right_count = sum(1 for c in centers if c >= page_width * 0.5)

        # 양쪽에 블록이 고루 분포하면 2단 컬럼으로 추정
        if left_count > 2 and right_count > 2:
            double_col_votes += 1

    if sample_pages > 0 and double_col_votes >= sample_pages * 0.6:
        return "double_column"
    return "single"


def has_formulas(doc: fitz.Document) -> bool:
    """PDF 내 수식 패턴 존재 여부를 감지한다."""
    sample_pages = min(10, len(doc))
    combined_pattern = re.compile("|".join(FORMULA_PATTERNS))

    for i in range(sample_pages):
        page = doc[i]
        text = page.get_text("text")
        if combined_pattern.search(text):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="PDF 메타데이터 감지")
    parser.add_argument("--pdf", required=True, help="분석할 PDF 파일 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"ERROR: PDF 파일을 찾을 수 없음: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    doc = fitz.open(args.pdf)
    pdf_type = detect_type(args.pdf)
    layout_type = detect_layout_type(doc)
    formula_detected = has_formulas(doc)
    page_count = len(doc)
    domain = parse_domain(args.pdf)
    doc.close()

    meta = {
        "type": pdf_type,
        "page_count": page_count,
        "layout_type": layout_type,
        "has_formulas": formula_detected,
        "domain": domain,
    }

    output_path = os.path.join(args.output, "pdf_meta.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"pdf_meta.json 저장 완료: {output_path}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
