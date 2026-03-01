#!/usr/bin/env python3
"""
ocr_preprocess.py
스캔된 PDF를 이미지로 변환 후 OCR을 실행해 검색 가능한 PDF를 생성한다.

출력: <output>/ocr_preprocessed.pdf
에러: 페이지별 신뢰도 < 80% 시 로그 기록 후 계속 진행
"""

import argparse
import json
import os
import sys
from typing import List, Tuple

try:
    from pdf2image import convert_from_path
except ImportError:
    print("ERROR: pdf2image not installed. Run: pip install pdf2image", file=sys.stderr)
    sys.exit(1)

try:
    import pytesseract
    from PIL import Image
except ImportError:
    print("ERROR: pytesseract / Pillow not installed. Run: pip install pytesseract Pillow", file=sys.stderr)
    sys.exit(1)

try:
    import fitz  # PyMuPDF - searchable PDF 생성에 사용
except ImportError:
    print("ERROR: PyMuPDF(fitz) not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

OCR_CONFIDENCE_THRESHOLD = 80


def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
    """PDF를 페이지별 PIL 이미지 리스트로 변환한다."""
    images = convert_from_path(pdf_path, dpi=dpi)
    print(f"  PDF → 이미지 변환 완료: {len(images)} 페이지")
    return images


def run_ocr(images: List[Image.Image]) -> List[Tuple[str, float]]:
    """
    이미지 리스트에 OCR을 실행한다.
    반환: [(text, confidence), ...] 페이지별
    """
    results = []
    for i, img in enumerate(images, start=1):
        # tesseract 데이터 딕셔너리로 신뢰도 추출
        data = pytesseract.image_to_data(img, lang="eng", output_type=pytesseract.Output.DICT)
        texts = data["text"]
        confs = data["conf"]

        # 신뢰도 >= 0인 단어만 필터링 (-1은 non-word 영역)
        valid = [(t, c) for t, c in zip(texts, confs) if c >= 0]
        if valid:
            avg_conf = sum(c for _, c in valid) / len(valid)
            page_text = " ".join(t for t, c in valid if t.strip())
        else:
            avg_conf = 0.0
            page_text = ""

        results.append((page_text, avg_conf))

        status = "OK" if avg_conf >= OCR_CONFIDENCE_THRESHOLD else "LOW_CONFIDENCE"
        print(f"  페이지 {i}: 평균 신뢰도 {avg_conf:.1f}% [{status}]")

    return results


def create_searchable_pdf(original_pdf: str, ocr_data: List[Tuple[str, float]], output_path: str) -> None:
    """
    원본 PDF 이미지에 OCR 텍스트 레이어를 삽입해 검색 가능한 PDF를 생성한다.
    신뢰도 낮은 페이지도 계속 처리하며 로그를 남긴다.
    """
    doc = fitz.open(original_pdf)
    low_confidence_pages = []

    for i, (text, confidence) in enumerate(ocr_data):
        if confidence < OCR_CONFIDENCE_THRESHOLD:
            low_confidence_pages.append({
                "page": i + 1,
                "confidence": round(confidence, 2),
            })

        page = doc[i]
        # 텍스트가 있을 때만 보이지 않는 텍스트 레이어 추가
        if text.strip():
            rect = page.rect
            page.insert_text(
                fitz.Point(0, rect.height - 10),
                text,
                fontsize=1,
                color=(1, 1, 1),  # 흰색 = 보이지 않음
                overlay=False,
            )

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    print(f"  검색 가능 PDF 저장: {output_path}")

    if low_confidence_pages:
        log_path = os.path.join(os.path.dirname(output_path), "ocr_low_confidence.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(low_confidence_pages, f, ensure_ascii=False, indent=2)
        print(f"  경고: {len(low_confidence_pages)}개 페이지 신뢰도 부족 → {log_path}")


def main():
    parser = argparse.ArgumentParser(description="스캔 PDF OCR 전처리")
    parser.add_argument("--pdf", required=True, help="입력 PDF 파일 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"ERROR: PDF 파일을 찾을 수 없음: {args.pdf}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    output_pdf = os.path.join(args.output, "ocr_preprocessed.pdf")

    print(f"[OCR 전처리] {args.pdf}")
    images = pdf_to_images(args.pdf)
    ocr_data = run_ocr(images)
    create_searchable_pdf(args.pdf, ocr_data, output_pdf)
    print("[OCR 전처리] 완료")


if __name__ == "__main__":
    main()
