# Skill: pdf-composer

## 목적
번역 완료된 JSON과 에셋 이미지를 합쳐 한국어 번역 PDF 초안을 생성한다.
텍스트 오버플로우 시 폰트 크기 자동 축소 후 잘라내기 + 로그 기록.

---

## 입력 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `layout_path` | ✓ | layout_map.json 파일 경로 |
| `translation_path` | ✓ | translation_final.json 파일 경로 |
| `assets_dir` | ✓ | 에셋 이미지 디렉터리 경로 |
| `output_dir` | ✓ | 결과 파일을 저장할 디렉터리 |
| `font_path` | 선택 | 한글 TTF 폰트 경로 (기본: fonts/NanumGothic.ttf) |

---

## 호출 스크립트 명령어

```bash
# 기본 폰트 사용
python .claude/skills/pdf-composer/scripts/compose_pdf.py \
  --layout "{layout_path}" \
  --translation "{translation_path}" \
  --assets "{assets_dir}" \
  --output "{output_dir}"

# 커스텀 폰트 지정
python .claude/skills/pdf-composer/scripts/compose_pdf.py \
  --layout "{layout_path}" \
  --translation "{translation_path}" \
  --assets "{assets_dir}" \
  --output "{output_dir}" \
  --font "fonts/NanumGothic.ttf"
```

---

## 출력 파일

| 파일 | 설명 |
|------|------|
| `{output_dir}/translated_draft.pdf` | 한국어 번역 PDF 초안 |
| `{output_dir}/overflow_log.json` | 텍스트 오버플로우 발생 항목 (발생 시만) |

### overflow_log.json 스키마
```json
[
  {
    "page": 3,
    "bbox": [72.0, 100.0, 540.0, 200.0],
    "truncated_at": 150,
    "original_length": 320,
    "preview": "번역 텍스트의 처음 100자..."
  }
]
```

---

## 오버플로우 처리 정책

1. 기본 폰트 크기 11pt로 배치 시도
2. bbox에 맞지 않으면 8pt로 재시도
3. 8pt에서도 맞지 않으면 6pt로 재시도
4. 6pt에서도 안 맞으면 텍스트를 잘라내고 overflow_log.json에 기록

---

## 폰트 요구사항

- **NanumGothic.ttf** 파일이 `fonts/` 디렉터리에 있어야 한다.
- 없을 경우 Helvetica 폴백 (한글 깨짐 발생 가능).
- 다운로드: https://fonts.google.com/specimen/Nanum+Gothic

---

## 실패 시 처리

- translation_final.json 없음: 오케스트레이터에 에러 보고 (step=9, error_type=compose_error).
- 에셋 이미지 파일 없음: 해당 위치를 빈 공간으로 유지하고 WARNING 출력.
- reportlab 렌더링 오류: 해당 페이지 스킵, 로그 기록 후 계속 진행.
