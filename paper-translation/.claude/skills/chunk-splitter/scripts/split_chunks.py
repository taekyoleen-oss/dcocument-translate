#!/usr/bin/env python3
"""
split_chunks.py
layout_map.json을 읽어 번역 대상 요소를 청크로 분할한다.

번역 대상: text, table (formula_block/code/asset/formula_inline/caption 제외)
출력: <output>/chunks/chunk_{id}_source.json
  {id, section, page_range, elements: [{type, text, bbox, column, cells?}]}
"""

import argparse
import json
import os
import re
import sys

TRANSLATABLE_TYPES = {"text", "table", "section_header", "caption"}
NON_TRANSLATABLE_TYPES = {"formula_block", "code", "asset", "formula_inline"}

TOKEN_LIMIT = 1500

SECTION_HEADER_PATTERN = re.compile(
    r"^(\d+\.?\s+[A-Z]|\d+\s+[A-Z]|[IVX]+\.\s+[A-Z]|Abstract|Introduction|"
    r"Conclusion|References|Appendix|Method|Results|Discussion|Related Work|"
    r"Background|Experiment)"
)


def estimate_tokens(text: str) -> int:
    """단순 단어 수 기반 토큰 수 추정 (단어 수 × 1.3)."""
    words = len(text.split())
    return int(words * 1.3)


def detect_section_boundary(element: dict) -> bool:
    """
    요소가 섹션 경계인지 판별한다.
    기준: section_header 타입이거나 대문자 헤더/숫자 섹션 패턴 매칭.
    """
    if element.get("type") == "section_header":
        return True
    text = element.get("text", "")
    first_line = text.split("\n")[0].strip() if text else ""
    return bool(SECTION_HEADER_PATTERN.match(first_line))


def split_by_section(elements: list) -> list:
    """
    섹션 경계 기준으로 요소 그룹을 분할한다.
    반환: [[element, ...], ...]
    """
    groups = []
    current = []

    for elem in elements:
        if detect_section_boundary(elem) and current:
            groups.append(current)
            current = [elem]
        else:
            current.append(elem)

    if current:
        groups.append(current)

    return groups


def split_by_token_limit(elements: list, limit: int = TOKEN_LIMIT) -> list:
    """
    섹션 그룹 내 토큰 수가 초과되면 추가로 분할한다.
    반환: [[element, ...], ...]
    """
    chunks = []
    current = []
    current_tokens = 0

    for elem in elements:
        text = elem.get("text", "")
        if elem.get("type") == "table":
            cells = elem.get("cells", [])
            text = " ".join(str(c[2]) for c in cells if c[2])

        tokens = estimate_tokens(text) if text else 0

        if current and current_tokens + tokens > limit:
            chunks.append(current)
            current = [elem]
            current_tokens = tokens
        else:
            current.append(elem)
            current_tokens += tokens

    if current:
        chunks.append(current)

    return chunks


def get_page_range(elements: list) -> list:
    """청크 내 요소들의 페이지 범위 [min_page, max_page]를 반환한다."""
    pages = []
    for elem in elements:
        if "page" in elem:
            pages.append(elem["page"])
    if not pages:
        return [0, 0]
    return [min(pages), max(pages)]


def get_section_name(elements: list) -> str:
    """청크 첫 번째 섹션 헤더 텍스트를 반환한다."""
    for elem in elements:
        if elem.get("type") == "section_header":
            return elem.get("text", "").split("\n")[0].strip()
        if detect_section_boundary(elem):
            return elem.get("text", "").split("\n")[0].strip()
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="번역 청크 분할")
    parser.add_argument("--layout", required=True, help="layout_map.json 경로")
    parser.add_argument("--output", required=True, help="출력 디렉터리")
    args = parser.parse_args()

    if not os.path.isfile(args.layout):
        print(f"ERROR: layout_map.json을 찾을 수 없음: {args.layout}", file=sys.stderr)
        sys.exit(1)

    chunks_dir = os.path.join(args.output, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    with open(args.layout, "r", encoding="utf-8") as f:
        layout_map = json.load(f)

    # 페이지별 요소 수집 + 페이지 번호 주입
    all_elements = []
    for page_data in layout_map:
        page_num = page_data["page"]
        for elem in page_data["elements"]:
            if elem.get("type") in TRANSLATABLE_TYPES:
                elem_copy = dict(elem)
                elem_copy["page"] = page_num
                all_elements.append(elem_copy)

    # Step 1: 섹션 경계로 분할
    section_groups = split_by_section(all_elements)

    # Step 2: 토큰 제한으로 추가 분할
    final_chunks = []
    for group in section_groups:
        sub_chunks = split_by_token_limit(group, TOKEN_LIMIT)
        final_chunks.extend(sub_chunks)

    # Step 3: 청크 파일 저장
    for chunk_id, chunk_elems in enumerate(final_chunks):
        page_range = get_page_range(chunk_elems)
        section = get_section_name(chunk_elems)

        # 출력용 요소에서 임시 page 필드 유지
        chunk_data = {
            "id": chunk_id,
            "section": section,
            "page_range": page_range,
            "elements": chunk_elems,
        }

        filename = f"chunk_{chunk_id}_source.json"
        filepath = os.path.join(chunks_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, ensure_ascii=False, indent=2)

        token_count = sum(
            estimate_tokens(e.get("text", "") or " ".join(str(c[2]) for c in e.get("cells", [])))
            for e in chunk_elems
        )
        print(f"  청크 {chunk_id}: {len(chunk_elems)}개 요소, ~{token_count} 토큰, 섹션='{section}'")

    print(f"\n총 {len(final_chunks)}개 청크 생성 → {chunks_dir}")


if __name__ == "__main__":
    main()
