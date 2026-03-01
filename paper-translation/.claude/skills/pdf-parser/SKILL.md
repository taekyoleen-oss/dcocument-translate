# Skill: pdf-parser

## 목적
입력 PDF를 분석해 유형(digital/scanned), 레이아웃, 요소 분류를 수행한다.
스캔본이면 OCR 전처리를 먼저 실행한 뒤 레이아웃을 파싱한다.

---

## 입력 파라미터

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `pdf_path` | ✓ | 분석할 PDF 파일 경로 |
| `output_dir` | ✓ | 결과 파일을 저장할 디렉터리 |

---

## 호출 스크립트 명령어

### Step 1: PDF 유형 감지
```bash
python .claude/skills/pdf-parser/scripts/detect_pdf_type.py \
  --pdf "{pdf_path}" \
  --output "{output_dir}"
```
→ `{output_dir}/pdf_meta.json` 생성

### Step 2a: OCR 전처리 (pdf_meta.json의 type == "scanned"인 경우만)
```bash
python .claude/skills/pdf-parser/scripts/ocr_preprocess.py \
  --pdf "{pdf_path}" \
  --output "{output_dir}"
```
→ `{output_dir}/ocr_preprocessed.pdf` 생성
→ 이후 레이아웃 파싱은 `ocr_preprocessed.pdf`를 사용

### Step 2b: 레이아웃 파싱
```bash
# digital PDF인 경우:
python .claude/skills/pdf-parser/scripts/parse_layout.py \
  --pdf "{pdf_path}" \
  --output "{output_dir}"

# scanned PDF (OCR 완료 후):
python .claude/skills/pdf-parser/scripts/parse_layout.py \
  --pdf "{output_dir}/ocr_preprocessed.pdf" \
  --output "{output_dir}"
```
→ `{output_dir}/layout_map.json` 생성

---

## 출력 파일

| 파일 | 설명 |
|------|------|
| `{output_dir}/pdf_meta.json` | PDF 메타데이터 (type, page_count, layout_type, has_formulas, domain) |
| `{output_dir}/ocr_preprocessed.pdf` | OCR 처리된 PDF (스캔본만) |
| `{output_dir}/layout_map.json` | 페이지별 요소 분류 결과 |
| `{output_dir}/ocr_low_confidence.json` | OCR 신뢰도 낮은 페이지 목록 (발생 시) |

---

## 실패 시 처리

- `detect_pdf_type.py` 실패: PDF 파일 손상 또는 접근 권한 문제. 오케스트레이터에 에러 보고.
- `ocr_preprocess.py` 실패: Tesseract 미설치 가능성. `pip install pytesseract` + Tesseract 바이너리 확인.
- `parse_layout.py` 실패: 레이아웃 파싱 오류. error_log.json에 step=2, error_type=layout_parse_error 기록.
- 신뢰도 < 80% 페이지: 계속 진행하되 `ocr_low_confidence.json`에 기록. Human Review 시 확인 요청.
