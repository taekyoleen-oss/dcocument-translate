# Skill: asset-extractor

## 목적
layout_map.json에서 번역 제외 요소(formula_block, code, asset)를 PNG 이미지로 추출한다.
추출한 이미지는 PDF 조합 단계에서 원위치에 삽입된다.

---

## 입력 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `pdf_path` | ✓ | 원본 PDF 파일 경로 |
| `layout_path` | ✓ | layout_map.json 파일 경로 |
| `output_dir` | ✓ | 결과 파일을 저장할 디렉터리 |

---

## 호출 스크립트 명령어

```bash
python .claude/skills/asset-extractor/scripts/extract_assets.py \
  --pdf "{pdf_path}" \
  --layout "{layout_path}" \
  --output "{output_dir}"
```

---

## 출력 파일

| 파일 | 설명 |
|------|------|
| `{output_dir}/assets/fig_p{page}_{idx}.png` | 추출된 에셋 이미지 |
| `{output_dir}/assets_manifest.json` | 에셋 목록 [{id, page, bbox, filepath, caption, type}] |

### assets_manifest.json 스키마
```json
[
  {
    "id": 0,
    "page": 2,
    "bbox": [72.0, 150.0, 540.0, 400.0],
    "filepath": "output/{paper_id}/assets/fig_p2_3.png",
    "caption": "Figure 1: Architecture overview.",
    "type": "asset"
  }
]
```

---

## 추출 대상 타입

- `formula_block`: 독립 수식 블록
- `code`: 코드 블록
- `asset`: 그림, 다이어그램, 차트 등

제외 타입(번역 대상): `text`, `table`, `section_header`, `caption`, `formula_inline`

---

## 실패 시 처리

- 개별 요소 추출 실패: WARNING 출력 후 해당 요소를 건너뛰고 계속 진행.
- assets_manifest.json 저장 실패: error_log.json에 step=3, error_type=asset_extract_error 기록 후 오케스트레이터에 에러 보고.
- bbox가 유효하지 않은 경우: 해당 요소 스킵, 로그 기록.
