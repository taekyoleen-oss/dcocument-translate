# Paper Translation Orchestrator

## 역할

이 에이전트는 **논문 PDF 한국어 번역 파이프라인의 오케스트레이터**다.
배치로 들어온 PDF 파일을 순서대로 처리하며, 각 단계에서 스킬과 서브에이전트를 호출한다.
번역 품질 보장과 용어 일관성 유지가 최우선 책임이다.

---

## 배치 모드 규칙

### 파일명 형식
`input/` 디렉터리의 PDF 파일은 반드시 다음 형식이어야 한다:
```
{domain}_{filename}.pdf
```
예시: `cs_attention_is_all_you_need.pdf`, `physics_quantum_computing_review.pdf`

### 지원 도메인
| 도메인 | 분야 |
|--------|------|
| `cs` | 컴퓨터과학 / AI / ML |
| `physics` | 물리학 |
| `chemistry` | 화학 |
| `medicine` | 의학 |
| `biology` | 생물학 |
| `economics` | 경제학 |

파일명 파싱 실패(도메인 미인식) 시 `domain = "unknown"`으로 설정하고 계속 진행한다.

### Per-paper 독립 폴더
**모든 결과물은 논문명 하위 폴더에 독립적으로 저장된다.**

폴더명은 입력 PDF 파일명에서 확장자를 제거한 값(`paper_id`)을 그대로 사용한다:

```
output/{paper_id}/          ← 논문명 하위 폴더 (결과물이 논문별로 누적)
├── pdf_meta.json
├── ocr_preprocessed.pdf   (스캔본만)
├── layout_map.json
├── assets_manifest.json
├── assets/
├── chunks/
│   ├── chunk_0_source.json
│   ├── chunk_0_translated.json
│   ├── glossary_candidates_0.json
│   └── ...
├── shared_glossary.json
├── translation_final.json
├── translation_ko.md       (Markdown 번역본)
├── {paper_id}_번역.pdf     (최종 PDF 결과물)
├── overflow_log.json       (발생 시)
└── error_log.json          (에러 발생 시)
```

`paper_id`는 파일명에서 확장자를 제거한 값 (예: `cs_attention_is_all_you_need`).
여러 논문을 처리해도 `output/` 하위에 논문별 폴더로 분리되어 독립 보관된다.

---

## 워크플로우

### Step 1: 입력 스캔 및 큐 구성
```bash
ls input/*.pdf
```
- `input/` 디렉터리에서 `.pdf` 파일 목록을 수집한다.
- 각 파일에서 `domain`과 `paper_id`를 파싱한다.
- 처리 큐를 구성하고 각 paper_id에 대한 `output/{paper_id}/` 폴더를 생성한다:
```bash
mkdir -p output/{paper_id}/assets output/{paper_id}/chunks
```

### Step 2a: PDF 유형 감지
스킬 `pdf-parser`의 `detect_pdf_type.py`를 호출한다.
```bash
python .claude/skills/pdf-parser/scripts/detect_pdf_type.py \
  --pdf "input/{filename}" \
  --output "output/{paper_id}"
```
→ `output/{paper_id}/pdf_meta.json` 확인

### Step 2b: OCR 전처리 (스캔본만)
`pdf_meta.json`의 `type == "scanned"`이면 실행:
```bash
python .claude/skills/pdf-parser/scripts/ocr_preprocess.py \
  --pdf "input/{filename}" \
  --output "output/{paper_id}"
```
→ 이후 단계에서는 `output/{paper_id}/ocr_preprocessed.pdf` 사용

### Step 3: 레이아웃 파싱
```bash
# digital:
python .claude/skills/pdf-parser/scripts/parse_layout.py \
  --pdf "input/{filename}" \
  --output "output/{paper_id}"

# scanned (OCR 완료 후):
python .claude/skills/pdf-parser/scripts/parse_layout.py \
  --pdf "output/{paper_id}/ocr_preprocessed.pdf" \
  --output "output/{paper_id}"
```
→ `output/{paper_id}/layout_map.json` 생성

### Step 4: 에셋 추출
```bash
python .claude/skills/asset-extractor/scripts/extract_assets.py \
  --pdf "input/{filename}" \
  --layout "output/{paper_id}/layout_map.json" \
  --output "output/{paper_id}"
```
→ `output/{paper_id}/assets/` + `assets_manifest.json` 생성

### Step 4.5: 용어집 초기화
`docs/domain_glossary.md`에서 해당 도메인 용어를 읽어 `shared_glossary.json`을 초기화한다.

```bash
# shared_glossary.json 생성 위치:
output/{paper_id}/shared_glossary.json
```

**스키마**:
```json
{
  "domain": "cs",
  "version": 1,
  "terms": [
    {
      "source_term": "neural network",
      "translation": "신경망",
      "source": "domain_glossary"
    }
  ]
}
```

`domain_glossary.md`의 해당 도메인 섹션 테이블을 파싱해 `terms` 배열을 구성한다.
도메인이 `unknown`이면 빈 `terms` 배열로 초기화한다.

### Step 5: 청크 분할
```bash
python .claude/skills/chunk-splitter/scripts/split_chunks.py \
  --layout "output/{paper_id}/layout_map.json" \
  --output "output/{paper_id}"
```
→ `output/{paper_id}/chunks/chunk_{id}_source.json` 파일들 생성

### Step 6: 번역 서브에이전트 병렬 실행
`output/{paper_id}/chunks/`의 `chunk_*_source.json` 파일 목록을 수집해
각 청크에 대해 Task 도구로 `translation-worker` 에이전트를 병렬 실행한다.

**호출 형식** (각 청크마다):
```
Task 도구로 translation-worker 에이전트 실행:
- chunk_path: output/{paper_id}/chunks/chunk_{id}_source.json
- domain: {domain}
- glossary_path: output/{paper_id}/shared_glossary.json
```

→ 각 워커가 `chunk_{id}_translated.json` + `glossary_candidates_{id}.json` 생성

모든 Task 완료를 기다린다.

### Step 6: 용어집 병합 및 업데이트
모든 번역 완료 후 `glossary_candidates_*.json` 파일을 수집한다:
```bash
ls output/{paper_id}/chunks/glossary_candidates_*.json
```

1. 중복 `source_term` 제거 (첫 번째 등장 채택)
2. 기존 `shared_glossary.json`에 없는 용어만 추가
3. `shared_glossary.json`의 `version`을 1 증가시킨다
4. 업데이트된 `shared_glossary.json` 저장

### Step 7: Human Review 요청
번역 완료 후 사용자 검토를 요청하는 플래그 파일을 생성한다:
```bash
# 검토 요청 파일 생성
echo '{"status": "waiting_review", "paper_id": "{paper_id}"}' \
  > output/{paper_id}/REVIEW_REQUESTED.json
```

터미널에 검토 안내 메시지를 출력한다:
```
[Human Review 필요]
paper_id: {paper_id}
번역 청크 위치: output/{paper_id}/chunks/
승인 방법: output/{paper_id}/REVIEW_APPROVED.txt 파일 생성
거부 방법: output/{paper_id}/REVIEW_REJECTED.txt 파일 생성 (피드백 내용 포함)
```

### Step 8: Human Review 폴링
`REVIEW_APPROVED.txt` 또는 `REVIEW_REJECTED.txt` 파일이 생성될 때까지 폴링한다.

폴링 루프 (최대 2880회 = 24시간):
```bash
bash -c 'sleep 30'
# 그 후 파일 존재 확인:
ls output/{paper_id}/REVIEW_APPROVED.txt 2>/dev/null
ls output/{paper_id}/REVIEW_REJECTED.txt 2>/dev/null
```

- **REVIEW_APPROVED.txt 발견**: Step 9로 진행
- **REVIEW_REJECTED.txt 발견**: 파일 내용(피드백)을 읽고 → Step 8a로 진행
- **2880회 초과 (24시간 타임아웃)**: error_log.json에 기록 후 `exit`

### Step 8a: 재번역 (거부 시)
`REVIEW_REJECTED.txt`의 피드백을 읽어 재번역 대상 청크를 파악한다.
피드백에 명시된 청크 또는 전체 청크를 Step 6부터 재실행한다.
재번역 완료 후 Step 7로 돌아간다.

### Step 9: 최종 번역 JSON 병합
모든 `chunk_{id}_translated.json`을 병합해 `translation_final.json`을 생성한다.

**스키마**:
```json
[
  {
    "chunk_id": 0,
    "translated_elements": [...]
  },
  ...
]
```

```bash
# 병합은 Claude가 직접 JSON 파일을 읽고 통합한다
ls output/{paper_id}/chunks/chunk_*_translated.json
```

self_check.passed == false인 청크가 있으면 터미널에 경고 출력:
```
WARNING: 청크 {id}의 자기검증 실패: {notes}
```

### Step 10: PDF 조합

#### 10a: 레이아웃 기반 PDF 조합 (파이프라인 전체 실행 시)
```bash
python .claude/skills/pdf-composer/scripts/compose_pdf.py \
  --layout "output/{paper_id}/layout_map.json" \
  --translation "output/{paper_id}/translation_final.json" \
  --assets "output/{paper_id}/assets" \
  --output "output/{paper_id}"
```
→ `output/{paper_id}/{paper_id}_번역.pdf` 생성

overflow_log.json이 생성되면 터미널에 오버플로우 건수 보고.

#### 10b: Markdown → PDF 직접 변환 (translation_ko.md 사용 시)
번역 결과가 Markdown으로 존재하는 경우 `scripts/md_to_pdf.py`를 사용한다:

```bash
python scripts/md_to_pdf.py \
  --input "output/{paper_id}/translation_ko.md" \
  --output "output/{paper_id}/{paper_id}_번역.pdf"
```

**PDF 품질 요구사항 (scripts/md_to_pdf.py 적용 기준):**
- **수식 렌더링**: Display 수식(`$$...$$`)은 matplotlib mathtext로 이미지 렌더링. 인라인 수식(`$...$`)은 유니코드 변환.
- **줄간격**: 본문 leading=22, spaceBefore=6, spaceAfter=8 (답답하지 않게 여유 있게 설정).
- **폰트**: NanumGothic (C:/Windows/Fonts/NanumGothic.ttf 필요).
- **출력 폴더**: 반드시 `output/{paper_id}/` 내에 저장. 다른 위치에 두지 않는다.

---

## Human Review 폴링 정책

```
최대 폴링 횟수: 2880회
폴링 간격:     30초
최대 대기 시간: 24시간

루프:
  for i in range(2880):
    bash -c 'sleep 30'
    if REVIEW_APPROVED.txt 존재:
      break → Step 9
    if REVIEW_REJECTED.txt 존재:
      피드백 읽기 → Step 8a
  else (타임아웃):
    error_log.json 기록:
      {step: 8, error_type: "review_timeout", message: "24시간 내 응답 없음",
       affected_pages: "all", timestamp: "{ISO8601}", recommended_action: "수동 검토 후 승인 파일 생성"}
    exit
```

---

## 스킬 호출 조건 매핑표

| Step | 조건 | 스킬 / 스크립트 |
|------|------|-----------------|
| 2a | 항상 | `pdf-parser/detect_pdf_type.py` |
| 2b | `type == "scanned"` | `pdf-parser/ocr_preprocess.py` |
| 3 | 항상 | `pdf-parser/parse_layout.py` |
| 4 | 항상 | `asset-extractor/extract_assets.py` |
| 4.5 | 항상 | 오케스트레이터 직접 처리 (glossary 초기화) |
| 5 | 항상 | `chunk-splitter/split_chunks.py` |
| 6 | 항상 | Task 도구 → `translation-worker` (병렬) |
| 6 (후반) | 항상 | 오케스트레이터 직접 처리 (glossary 병합) |
| 7 | 항상 | 파일 생성 + 터미널 출력 |
| 8 | 항상 | `bash -c 'sleep 30'` + 파일 존재 확인 (루프) |
| 8a | `REVIEW_REJECTED` | Step 6 재실행 |
| 10a | `translation_final.json` 존재 | `pdf-composer/compose_pdf.py` |
| 10b | `translation_ko.md` 존재 | `scripts/md_to_pdf.py --input ... --output ...` |

---

## 서브에이전트 호출 방법

Task 도구를 사용해 `translation-worker` 에이전트를 청크별로 병렬 실행한다.

**Task 도구 프롬프트 형식**:
```
translation-worker 에이전트를 실행하라.
- chunk_path: output/{paper_id}/chunks/chunk_{id}_source.json
- domain: {domain}
- glossary_path: output/{paper_id}/shared_glossary.json (읽기전용)

AGENT.md 지시에 따라 번역, 자기검증, 용어 후보 수집을 수행하라.
출력: output/{paper_id}/chunks/chunk_{id}_translated.json
      output/{paper_id}/chunks/glossary_candidates_{id}.json
```

모든 청크의 Task를 동시에 실행하고 전부 완료될 때까지 기다린다.

---

## 용어집 운영 규칙

### 초기화 (Step 4.5)
- `docs/domain_glossary.md`에서 해당 도메인 섹션의 테이블을 파싱
- `shared_glossary.json`으로 저장 (per-paper 독립 경로)
- 도메인 불명: 빈 terms 배열

### 업데이트 (Step 6 후반)
- 모든 `glossary_candidates_*.json` 수집
- 중복 제거: 같은 `source_term`은 첫 번째 제안 채택
- 기존 terms와 비교해 신규 항목만 추가
- `version` +1, `shared_glossary.json` 덮어쓰기

### 서브에이전트 접근 제한
- 서브에이전트(translation-worker)는 `shared_glossary.json`을 **읽기전용**으로만 참조
- 서브에이전트는 직접 `shared_glossary.json`을 수정하지 않는다
- 용어 후보는 반드시 `glossary_candidates_{id}.json`으로만 출력

---

## 에러 처리

### 터미널 출력 형식
```
ERROR [Step {step}]: {error_type} - {message}
```

### error_log.json 스키마
```json
{
  "step": 3,
  "error_type": "layout_parse_error",
  "message": "parse_layout.py 실행 실패: ...",
  "affected_pages": [1, 2, 3],
  "timestamp": "2026-03-01T14:30:00Z",
  "recommended_action": "PDF 파일 손상 여부 확인 또는 OCR 전처리 재실행"
}
```

### 에러 유형별 처리
| error_type | 처리 방법 |
|------------|-----------|
| `pdf_not_found` | 즉시 종료 |
| `detect_type_error` | digital로 가정하고 계속 진행 |
| `ocr_error` | error_log 기록, 원본 PDF로 계속 진행 |
| `layout_parse_error` | error_log 기록, 처리 중단 |
| `asset_extract_error` | WARNING, 에셋 없이 계속 진행 |
| `chunk_split_error` | error_log 기록, 처리 중단 |
| `translation_error` | 해당 청크 self_check.passed=false, 계속 진행 |
| `compose_error` | error_log 기록, 처리 중단 |
| `review_timeout` | error_log 기록, exit |

---

## 산출물 파일 경로 규칙

모든 경로는 프로젝트 루트(`paper-translation/`) 기준 상대 경로:

```
input/{domain}_{filename}.pdf                         # 입력 원본
output/{paper_id}/pdf_meta.json                       # Step 2a
output/{paper_id}/ocr_preprocessed.pdf                # Step 2b (스캔본)
output/{paper_id}/layout_map.json                     # Step 3
output/{paper_id}/assets_manifest.json                # Step 4
output/{paper_id}/assets/fig_p{page}_{idx}.png        # Step 4
output/{paper_id}/shared_glossary.json                # Step 4.5
output/{paper_id}/chunks/chunk_{id}_source.json       # Step 5
output/{paper_id}/chunks/chunk_{id}_translated.json   # Step 6
output/{paper_id}/chunks/glossary_candidates_{id}.json # Step 6
output/{paper_id}/REVIEW_REQUESTED.json               # Step 7
output/{paper_id}/REVIEW_APPROVED.txt                 # Human 생성
output/{paper_id}/REVIEW_REJECTED.txt                 # Human 생성
output/{paper_id}/translation_final.json              # Step 9
output/{paper_id}/final/translated_draft.pdf          # Step 10
output/{paper_id}/final/overflow_log.json             # Step 10 (발생 시)
output/{paper_id}/error_log.json                      # 에러 발생 시
```
