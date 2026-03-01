#!/usr/bin/env python3
"""
extract_assets.py
layout_map.json을 참조해 formula_block, code, asset 타입 요소를 이미지로 추출한다.

출력:
  <output>/assets/fig_p{page}_{idx}.png
  <output>/assets_manifest.json
    [{id, page, bbox, filepath, caption, type}]
"""

import argparse
import json
import os
import sys

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF(fitz) not installed. Run: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(1)

EXTRACTABLE_TYPES = {"formula_block", "code", "asset"}


def crop_element(doc: fitz.Document, page_num: int, bbox: list, dpi: int = 200) -> Image.Image:
    """
    PDF의 지정 페이지와 bbox 영역을 크롭해 PIL 이미지로 반환한다.
    page_num은 1-indexed.
    """
    page = doc[page_num - 1]
    rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 DPI → target DPI
    clip = rect
    pix = page.get_pixmap(matrix=mat, clip=clip)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img


def save_asset(image: Image.Image, assets_dir: str, page: int, idx: int) -> str:
    """이미지를 PNG로 저장하고 파일 경로를 반환한다."""
    filename = f"fig_p{page}_{idx}.png"
    filepath = os.path.join(assets_dir, filename)
    image.save(filepath, "PNG")
    return filepath


def find_caption(elements: list, elem_bbox: list) -> str:
    """
    같은 페이지의 caption 요소 중 해당 요소 bbox 바로 아래에 있는 캡션을 찾는다.
    """
    _, _, _, y1 = elem_bbox
    for other in elements:
        if other.get("type") == "caption":
            other_bbox = other.get("bbox", [])
            if other_bbox and abs(other_bbox[1] - y1) < 50:  # 50pt 이내
                return other.get("text", "")
    return ""


def main():
    parser = argparse.ArgumentParser(description="PDF 에셋 추출")
    parser.add_argument("--pdf", required=True, help="입력 PDF 파일 경로")
    parser.add_argument("--layout", required=True, help="layout_map.json 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        print(f"ERROR: PDF 파일을 찾을 수 없음: {args.pdf}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(args.layout):
        print(f"ERROR: layout_map.json을 찾을 수 없음: {args.layout}", file=sys.stderr)
        sys.exit(1)

    assets_dir = os.path.join(args.output, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    with open(args.layout, "r", encoding="utf-8") as f:
        layout_map = json.load(f)

    doc = fitz.open(args.pdf)
    manifest = []
    asset_id = 0

    for page_data in layout_map:
        page_num = page_data["page"]
        elements = page_data["elements"]

        for idx, elem in enumerate(elements):
            elem_type = elem.get("type")
            if elem_type not in EXTRACTABLE_TYPES:
                continue

            bbox = elem.get("bbox")
            if not bbox or len(bbox) < 4:
                continue

            try:
                image = crop_element(doc, page_num, bbox)
                filepath = save_asset(image, assets_dir, page_num, idx)
                caption = find_caption(elements, bbox)

                manifest.append({
                    "id": asset_id,
                    "page": page_num,
                    "bbox": bbox,
                    "filepath": filepath,
                    "caption": caption,
                    "type": elem_type,
                })
                asset_id += 1
                print(f"  추출: 페이지 {page_num}, 요소 {idx} [{elem_type}] → {os.path.basename(filepath)}")

            except Exception as e:
                print(f"  WARNING: 페이지 {page_num} 요소 {idx} 추출 실패: {e}", file=sys.stderr)

    doc.close()

    manifest_path = os.path.join(args.output, "assets_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nassets_manifest.json 저장 완료: {manifest_path}")
    print(f"총 {asset_id}개 에셋 추출")


if __name__ == "__main__":
    main()
