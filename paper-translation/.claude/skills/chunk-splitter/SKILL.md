# Skill: chunk-splitter

## 목적
layout_map.json의 번역 대상 요소를 1500 토큰 이하의 청크로 분할한다.
번역 서브에이전트가 청크 단위로 독립적으로 작동할 수 있도록 JSON 파일을 생성한다.

---

## 입력 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `layout_path` | ✓ | layout_map.json 파일 경로 |
| `output_dir` | ✓ | 결과 파일을 저장할 디렉터리 |

---

## 호출 스크립트 명령어

```bash
python .claude/skills/chunk-splitter/scripts/split_chunks.py \
  --layout "{layout_path}" \
  --output "{output_dir}"
```

---

## 출력 파일

| 파일 | 설명 |
|------|------|
| `{output_dir}/chunks/chunk_{id}_source.json` | 청크별 번역 소스 파일 |

### chunk_{id}_source.json 스키마
```json
{
  "id": 0,
  "section": "1. Introduction",
  "page_range": [1, 3],
  "elements": [
    {
      "type": "text",
      "bbox": [72.0, 100.0, 540.0, 200.0],
      "column": 0,
      "text": "This paper presents...",
      "page": 1
    },
    {
      "type": "table",
      "bbox": [72.0, 220.0, 540.0, 350.0],
      "column": 0,
      "cells": [[0, 0, "Method"], [0, 1, "Accuracy"]],
      "page": 2
    }
  ]
}
```

---

## 분할 규칙

1. **섹션 경계 우선**: 섹션 헤더(숫자 섹션, Abstract, Introduction 등) 기준으로 1차 분할
2. **토큰 제한**: 섹션 내 토큰이 1500 초과 시 추가 분할 (추정: 단어 수 × 1.3)
3. **번역 대상**: `text`, `table`, `section_header`, `caption` 타입만 포함
4. **제외**: `formula_block`, `code`, `asset`, `formula_inline` 타입 제외

---

## 실패 시 처리

- layout_map.json 파싱 실패: 오케스트레이터에 에러 보고 (step=4, error_type=chunk_split_error).
- 빈 청크 생성: 자동으로 건너뜀.
- 단일 요소가 1500 토큰 초과: 해당 요소를 단독 청크로 생성 (분할 불가).
