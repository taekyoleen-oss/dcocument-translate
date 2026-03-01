# 영문 논문 PDF → 한국어 번역 PDF 에이전트 시스템 설계서

> Claude Code 구현 참조용 계획서
> 작성 기준일: 2026-03-01
> 최종 업데이트: 2026-03-01 (7라운드 심층 인터뷰 반영)

---

## 1. 작업 컨텍스트

### 배경 및 목적

영문 학술 논문 PDF를 한국어로 번역하여, 원문 레이아웃을 최대한 보존한 고품질 한국어 PDF로 아카이빙한다. 번역 과정에서 사람의 검토 포인트를 두어 품질을 보장하고, 최종 산출물은 장기 보관 목적에 맞는 깔끔한 서식을 유지한다.

### 입력

- 영문 학술 논문 PDF (디지털 텍스트 레이어 있는 파일 또는 스캔본)
- 논문 분야 정보 (파일명 접두사 `{domain}_{filename}.pdf` 형식으로 지정, 또는 별도 전달)
- (수정 루프 시) 사람이 지정한 수정 위치 및 수정 내용 텍스트

### 출력

- 한국어 번역 PDF (원문 레이아웃 보존)
- 추출된 이미지/다이어그램 파일 모음 (`/output/assets/`)
- 번역 중간 결과물 JSON (`/output/chunks/`)
- 공유 용어집 (`/output/shared_glossary.json`)
- 오류 로그 (`/output/error_log.json`)

### 주요 제약조건

- **인라인 수식(formula_inline)**: LaTeX 원문 텍스트 그대로 보존 (이미지 변환 없음)
- **블록 수식(formula_block)**: 이미지로 crop 보존, 번역 대상 제외
- **코드 블록(code)**: 이미지로 crop 보존, 번역 대상 제외 (의사코드, 코드 스니펫 포함)
- **표(table)**: 번역 대상 포함. 셀 텍스트를 2D 배열로 추출하여 번역 후 재구성
- **이미지·다이어그램(asset)**: 번역 대상 제외, 원본 이미지 그대로 삽입
- 번역 품질 기준: 분야별 한국어 표준 용어 우선 사용 (shared_glossary.json 참조)
- 스캔본의 경우 OCR 선처리 필수
- 2단 컬럼 레이아웃 논문의 경우 읽기 순서(좌→우, 위→아래) 올바르게 파싱
- PDF 재조판 폰트: 나눔고딕(NanumGothic.ttf) 단일 고정

### 용어 정의

| 용어 | 정의 |
|------|------|
| **청크(chunk)** | 번역 단위로 분할된 텍스트 블록 (보통 섹션 단위) |
| **레이아웃 맵** | 원문 PDF의 페이지별 요소 위치 정보 (JSON) |
| **에셋(asset)** | 논문에서 추출된 그림, 다이어그램 이미지 파일 (표 제외) |
| **재조판** | 번역된 텍스트를 원문 레이아웃에 맞게 PDF로 재구성하는 작업 |
| **공유 용어집** | 논문 전체에서 일관성 있게 사용할 전문 용어 목록 (shared_glossary.json) |
| **column** | 2단 레이아웃에서 요소의 위치: 0=전체 너비, 1=좌단, 2=우단 |

---

## 2. 워크플로우 정의

### 전체 흐름

```
[START]
   │
   ▼
Step 1: PDF 입력 및 유형 감지
   │  ├─ 디지털 PDF → Step 2a (직접 파싱)
   │  └─ 스캔본 → Step 2b (OCR 선처리) → Step 2a
   ▼
Step 2: 레이아웃 분석 및 요소 분류
   │  (text / formula_inline / formula_block / code / table / asset 분류)
   │  (각 요소에 column 필드 부여: 0=전체, 1=좌, 2=우)
   ▼
Step 3: 에셋 추출 및 저장
   │  (formula_block, code → crop 이미지 저장)
   │  (asset → crop 이미지 저장)
   │  (formula_inline, table, text → crop 없음)
   ▼
Step 4: [HUMAN REVIEW] 에셋 누락 검토
   │  (폴링 간격: 30초 / 최대 대기: 24시간)
   │  ├─ 승인 → Step 4.5
   │  └─ 누락 발견 → Step 3 재실행 (해당 페이지 지정)
   ▼
Step 4.5: Pre-pass 용어 추출 (공유 용어집 초기화)
   │  (전체 텍스트에서 전문 용어 후보 추출 → shared_glossary.json 초기화)
   ▼
Step 5: 텍스트 청크 분할 및 병렬 번역
   │  (섹션 단위 분할 → 서브에이전트 병렬 실행)
   │  (서브에이전트: shared_glossary.json 읽기 전용 참조)
   │  (서브에이전트: 신규 용어 후보 → glossary_candidates_{id}.json 저장)
   ▼
Step 6: 번역 결과 취합 및 검증
   │  (용어 후보 취합 → shared_glossary.json 업데이트)
   │  (전체 translation_final.json LLM 검증 → 불일치 청크 재번역 1회)
   │  ├─ 검증 통과 → Step 7
   │  └─ 검증 실패 → 해당 청크 재번역 (최대 1회)
   ▼
Step 7: PDF 재조판 (레이아웃 맵 + 번역 텍스트 + 에셋 합성)
   │  (폰트: 나눔고딕 고정 / 오버플로우: 폰트 축소 → 속역 제거 → overflow_log.json)
   │  (표: 2D 배열 → 셀 텍스트 재배치)
   ▼
Step 8: [HUMAN REVIEW] 최종 번역 결과 검토
   │  (폴링 간격: 30초 / 최대 대기: 24시간)
   │  ├─ 승인 → Step 9
   │  └─ 수정 요청 → Step 8a (부분 재번역) → Step 7 (재조판)
   ▼
Step 9: 최종 PDF 저장 및 아카이빙
   │
[END]
```

### 단계별 상세 정의

#### Step 1: PDF 입력 및 유형 감지

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **입력** | PDF 파일 경로 |
| **처리** | 텍스트 레이어 존재 여부 감지, 스캔본 판별. 파일명 접두사에서 domain 추출 (`{domain}_{filename}.pdf` → domain 파싱; 접두사 없으면 "general") |
| **출력** | `pdf_meta.json` (파일 유형, 페이지 수, 감지된 레이아웃 유형, domain) |
| **성공 기준** | PDF 열기 성공, 유형 분류 완료 |
| **검증 방법** | 스키마 검증 (pdf_meta.json 필수 필드 존재) |
| **실패 처리** | 에스컬레이션: 터미널 즉시 출력 + error_log.json 기록 후 종료 |

#### Step 2a: 레이아웃 분석 및 요소 분류

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (파싱) + 에이전트 (요소 분류 검수) |
| **처리** | 페이지별 텍스트 블록, 수식 영역, 이미지 영역, 코드 블록, 표 영역 좌표 추출. 2단 컬럼 감지 시 읽기 순서 보정 및 column 필드 부여 |
| **요소 타입 분류** | `text` / `formula_inline` / `formula_block` / `code` / `table` / `asset` |
| **column 필드** | `0` = 전체 너비(단일 컬럼 포함), `1` = 좌단, `2` = 우단 |
| **코드 블록 감지** | 폰트명(Courier/Mono 계열) + bbox 너비-높이 비율 기반 휴리스틱 |
| **formula_inline 감지** | 인라인 수식: 텍스트 줄 안에 포함된 LaTeX 패턴. 이미지화 없이 원문 텍스트 보존 |
| **출력** | `layout_map.json` (페이지별 요소 위치 및 유형, column 필드 포함) |
| **성공 기준** | 모든 페이지의 요소가 6가지 타입 중 하나로 분류됨 |
| **검증 방법** | 규칙 기반 (분류되지 않은 영역 0개) |
| **실패 처리** | 자동 재시도 1회 → 실패 시 에스컬레이션 |

#### Step 2b: OCR 선처리 (스캔본 한정)

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (OCR 라이브러리) |
| **처리** | 페이지 이미지 → 텍스트 레이어 생성 |
| **출력** | OCR 처리된 PDF (텍스트 레이어 삽입) |
| **성공 기준** | 텍스트 신뢰도 평균 80% 이상 |
| **검증 방법** | 규칙 기반 (OCR 신뢰도 점수) |
| **실패 처리** | 스킵 + 로그 (페이지 단위, 저신뢰도 페이지는 로그에 기록 후 계속 진행) |

#### Step 3: 에셋 추출 및 저장

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **처리** | layout_map의 타입별 처리: `formula_block` → crop 이미지 저장, `code` → crop 이미지 저장, `asset` → crop 이미지 저장. `formula_inline` / `table` / `text` → crop 없음 |
| **출력** | `/output/assets/fig_p{page}_{idx}.png` 형식 파일들, `assets_manifest.json` |
| **성공 기준** | layout_map의 formula_block + code + asset 항목 수 = 실제 저장된 파일 수 |
| **검증 방법** | 규칙 기반 (manifest 카운트 일치 확인) |
| **실패 처리** | 자동 재시도 1회 → 실패 시 에스컬레이션 |

#### Step 4: [HUMAN REVIEW] 에셋 누락 검토

| 항목 | 내용 |
|------|------|
| **처리 주체** | 사람 |
| **제공 정보** | `/output/assets/` 폴더의 이미지 목록, `assets_manifest.json`, 원본 PDF |
| **검토 내용** | 그림·다이어그램·코드 블록·수식 블록 누락 여부, 잘못 crop된 이미지 여부 |
| **승인 방법** | `review_step4.txt`에 "APPROVED" 또는 누락된 페이지 번호 기재 |
| **폴링 방식** | 메인 에이전트 직접 폴링 (sleep + 파일 확인 루프) |
| **폴링 간격** | 30초 |
| **최대 대기 시간** | 24시간 |
| **타임아웃 처리** | 에스컬레이션: error_log.json에 기록 후 종료 |

#### Step 4.5: Pre-pass 용어 추출 (공유 용어집 초기화)

| 항목 | 내용 |
|------|------|
| **처리 주체** | 메인 에이전트 (LLM) |
| **진입 조건** | Step 4 APPROVED 직후 |
| **처리** | 전체 텍스트 청크(text, table 타입)에서 전문 용어 후보 추출 → `/docs/domain_glossary.md`의 기존 용어와 합산하여 `shared_glossary.json` 초기화 |
| **출력** | `/output/shared_glossary.json` |
| **스키마** | `[{source_term, translated_term, domain, first_seen_chunk}]` |
| **성공 기준** | shared_glossary.json 파일 생성 완료 |
| **실패 처리** | 빈 파일로 초기화 후 계속 진행 (용어집 없어도 번역 가능) |

#### Step 5: 텍스트 청크 분할 및 병렬 번역

| 항목 | 내용 |
|------|------|
| **처리 주체** | 메인 에이전트 (청크 분할 및 오케스트레이션) + 번역 서브에이전트 (병렬) |
| **처리** | layout_map의 텍스트/표 블록을 섹션 단위 청크로 분할 → 각 청크를 번역 서브에이전트에 배분 |
| **청크 크기 기준** | 섹션(Section) 단위. 섹션이 없으면 ~1,500 토큰 단위 분할 |
| **번역 기준** | shared_glossary.json 읽기 전용 참조. 분야별 한국어 표준 용어 우선. formula_block·code는 원문 유지 |
| **용어 후보 수집** | 각 서브에이전트는 번역 중 발견한 신규 전문 용어 후보를 `/output/chunks/glossary_candidates_{id}.json`에 저장 |
| **출력** | `/output/chunks/chunk_{id}_source.json` (청크 소스), `/output/chunks/chunk_{id}_translated.json` (원문, 번역문, 청크 위치 정보, 자기검증 결과 포함) |
| **성공 기준** | 모든 청크 번역 완료, 각 청크의 번역문이 비어있지 않음 |
| **검증 방법** | LLM 자기검증 (번역 서브에이전트가 각 청크 번역 후 자기검증: 누락 문장 없는지, 표준 용어 사용 여부) |
| **실패 처리** | 자동 재시도 최대 2회 → 이후에도 실패 시 해당 청크 에스컬레이션 |

#### Step 6: 번역 결과 취합 및 일관성 검증

| 항목 | 내용 |
|------|------|
| **처리 주체** | 메인 에이전트 |
| **처리 (취합)** | 모든 청크 취합, glossary_candidates_{id}.json 파일 전체 병합 → shared_glossary.json 업데이트 (쓰기). 사용자는 `/output/glossary_review.md`에서 확정 용어 검토 가능 |
| **처리 (검증)** | LLM이 translation_final.json 전체를 읽고 용어 일관성 판단 (50 chunks 이하). 50 chunks 초과 시 섹션별 샘플링으로 대체 |
| **출력** | `translation_final.json` (전체 청크 순서대로 병합), `shared_glossary.json` (업데이트), `glossary_review.md` |
| **성공 기준** | 청크 순서 누락 없음, 동일 원문 용어가 논문 전체에서 동일하게 번역됨 |
| **검증 방법** | 규칙 기반 (청크 ID 연속성) + LLM 전체 검증 (용어 일관성) |
| **실패 처리** | 불일치 용어 포함 청크 자동 재번역 1회 |

#### Step 7: PDF 재조판

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 (`compose_pdf.py`) |
| **처리** | layout_map + translation_final.json + assets를 합성하여 한국어 PDF 생성 |
| **폰트** | 나눔고딕(NanumGothic.ttf) 단일 고정 |
| **레이아웃 유지 방식** | 원문의 텍스트 블록 위치·크기 기준으로 한국어 텍스트 배치 |
| **오버플로우 처리** | 1차: 폰트 크기 자동 축소 (최소 권장 6pt). 2차: 폰트 축소로 해결 불가 시 텍스트 잘라내기(속역 제거). 잘린 내용은 `overflow_log.json`에 기록 |
| **표 재구성** | table 타입 요소의 2D 배열 데이터를 기반으로 셀별 번역 텍스트 재배치. 셀 병합 추출 실패 시 asset 이미지로 fallback |
| **formula_inline 처리** | LaTeX 원문 텍스트를 그대로 배치 (렌더링 없음, 한계 명시됨) |
| **출력** | `/output/translated_draft.pdf`, `/output/overflow_log.json` (오버플로우 발생 시) |
| **성공 기준** | PDF 생성 성공, 페이지 수 원문과 동일하거나 ±2 이내 |
| **검증 방법** | 스키마 검증 (PDF 유효성) + 규칙 기반 (페이지 수 체크) |
| **실패 처리** | 자동 재시도 1회 → 실패 시 에스컬레이션 |

#### Step 8: [HUMAN REVIEW] 최종 번역 검토

| 항목 | 내용 |
|------|------|
| **처리 주체** | 사람 |
| **제공 정보** | `translated_draft.pdf`, `overflow_log.json` (있는 경우) |
| **검토 내용** | 번역 품질, 용어 적절성, 레이아웃 이상 여부 |
| **승인 방법** | `review_step8.txt`에 "APPROVED" 또는 수정 지시 기재 |
| **수정 지시 형식** | `페이지번호 \| 원문 텍스트 일부 \| 수정 요청 내용` (한 줄에 하나) |
| **폴링 방식** | 메인 에이전트 직접 폴링 (sleep + 파일 확인 루프) |
| **폴링 간격** | 30초 |
| **최대 대기 시간** | 24시간 |
| **타임아웃 처리** | 에스컬레이션: error_log.json에 기록 후 종료 |

#### Step 8a: 부분 재번역 (수정 요청 시)

| 항목 | 내용 |
|------|------|
| **처리 주체** | 번역 서브에이전트 |
| **처리** | review_step8.txt의 수정 지시를 파싱 → 해당 청크 식별 → 지시 내용 반영하여 재번역 |
| **출력** | 수정된 청크 JSON → translation_final.json 업데이트 → Step 7 재실행 |
| **성공 기준** | 수정 지시된 모든 항목이 반영됨 |
| **검증 방법** | LLM 자기검증 (수정 지시 항목 반영 여부 체크리스트) |
| **실패 처리** | 에스컬레이션 (지시 내용이 모호하거나 처리 불가한 경우) |

#### Step 9: 최종 저장 및 아카이빙

| 항목 | 내용 |
|------|------|
| **처리 주체** | 스크립트 |
| **처리** | 최종 PDF를 `/output/final/` 에 원문 파일명 기반으로 저장, 메타데이터 기록 |
| **출력** | `/output/final/{원문파일명}_ko.pdf`, `archive_log.json` |

---

## 3. 구현 스펙

### 3.1 폴더 구조

#### 단일 논문 처리 시

```
/paper-translation
  ├── CLAUDE.md                              # 메인 에이전트 지침 (오케스트레이터)
  ├── /.claude
  │   ├── /skills
  │   │   ├── /pdf-parser
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       ├── detect_pdf_type.py     # 디지털/스캔본 감지, domain 파싱
  │   │   │       ├── ocr_preprocess.py      # OCR 선처리
  │   │   │       └── parse_layout.py        # 레이아웃 분석 및 요소 분류 (column 포함)
  │   │   ├── /asset-extractor
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       └── extract_assets.py      # formula_block/code/asset crop 추출
  │   │   ├── /chunk-splitter
  │   │   │   ├── SKILL.md
  │   │   │   └── /scripts
  │   │   │       └── split_chunks.py        # 텍스트/표 청크 분할
  │   │   └── /pdf-composer
  │   │       ├── SKILL.md
  │   │       └── /scripts
  │   │           └── compose_pdf.py         # 번역 결과 → PDF 재조판 (나눔고딕)
  │   └── /agents
  │       └── /translation-worker
  │           └── AGENT.md                   # 번역 서브에이전트 지침
  ├── /input                                 # 원본 PDF 배치 폴더
  ├── /output
  │   ├── /assets                            # 추출된 이미지 에셋 (formula_block, code, asset)
  │   ├── /chunks                            # 청크별 번역 결과 JSON
  │   │   ├── chunk_{id}_source.json
  │   │   ├── chunk_{id}_translated.json
  │   │   └── glossary_candidates_{id}.json  # 서브에이전트별 신규 용어 후보
  │   ├── /final                             # 최종 아카이빙 PDF
  │   ├── pdf_meta.json
  │   ├── layout_map.json
  │   ├── assets_manifest.json
  │   ├── shared_glossary.json               # 공유 용어집 (Step 4.5 초기화, Step 6 업데이트)
  │   ├── glossary_review.md                 # 사용자 용어 검토용 (Step 6 생성)
  │   ├── translation_final.json
  │   ├── translated_draft.pdf
  │   ├── overflow_log.json                  # 오버플로우로 잘린 텍스트 기록
  │   ├── error_log.json                     # 에스컬레이션 에러 기록
  │   ├── review_step4.txt                   # Human review 입력 파일
  │   └── review_step8.txt                   # Human review 입력 파일
  └── /docs
      └── domain_glossary.md                 # (선택) 분야별 표준 용어 참조
```

#### 배치 모드 처리 시 (다수 논문)

파일명 규칙: `{domain}_{filename}.pdf`
지원 domain 접두사: `cs`, `physics`, `chemistry`, `medicine`, `biology`, `economics`
접두사 없을 경우: domain = "general"

```
/paper-translation
  ├── /input
  │   ├── cs_attention_is_all_you_need.pdf
  │   └── physics_standard_model.pdf
  └── /output
      ├── /cs_attention_is_all_you_need      # 논문별 독립 출력 폴더
      │   ├── /assets
      │   ├── /chunks
      │   ├── /final
      │   ├── layout_map.json
      │   ├── shared_glossary.json
      │   ├── translation_final.json
      │   ├── overflow_log.json
      │   ├── error_log.json
      │   ├── review_step4.txt               # 논문별 독립 Human review 파일
      │   └── review_step8.txt
      └── /physics_standard_model
          └── ...
```

배치 처리 시 각 논문마다 독립적으로 에러 처리. 한 논문 실패 시 error_log.json 기록 후 다음 논문 계속 진행.

### 3.2 CLAUDE.md 핵심 섹션 목록

- **역할**: 오케스트레이터. 워크플로우 전체 진행 관리
- **워크플로우 단계 목록 및 순서** (Step 4.5 포함)
- **Human Review 대기 방법**: 폴링 정책 (30초 간격, 최대 24시간)
- **서브에이전트 호출 조건 및 방법**
- **스킬 호출 조건 매핑표** (데이터 주도 조건표)
- **중간 산출물 파일 경로 규칙**
- **에러 처리 및 에스컬레이션 기준** (error_log.json 포맷 포함)
- **배치 모드 규칙** (파일명 접두사 파싱, per-paper 독립 폴더 생성)
- **용어집 운영 규칙** (Step 4.5 초기화, Step 6 업데이트, 서브에이전트 읽기 전용)

### 3.3 에이전트 구조

**멀티 에이전트** 구조 채택. 번역 작업은 청크 단위로 독립적이며 병렬 처리 이득이 크므로 서브에이전트로 분리한다.

```
메인 에이전트 (CLAUDE.md)
└── 오케스트레이터: 전체 워크플로우 진행, 스크립트 호출, 서브에이전트 배분
    └── translation-worker (AGENT.md) × N개 병렬
        └── 각 청크 번역 + 자기검증 + 용어 후보 수집 담당
```

### 3.4 스킬 목록

| 스킬명 | 역할 | 트리거 조건 |
|--------|------|------------|
| `pdf-parser` | PDF 유형 감지, domain 파싱, OCR 선처리, 레이아웃 분석 (column 필드 포함) | Step 1–2 진입 시 |
| `asset-extractor` | formula_block/code/asset crop 추출 | Step 3 진입 시 (layout_map.json 준비된 후) |
| `chunk-splitter` | 텍스트/표 블록을 번역 단위 청크로 분할 | Step 5 진입 시 (Step 4 APPROVED 후) |
| `pdf-composer` | 번역 결과 + 에셋 + 레이아웃 맵으로 PDF 재조판 (나눔고딕) | Step 7 진입 시 (translation_final.json 준비된 후), Step 8a 후 재실행 시 |

### 3.5 서브에이전트: translation-worker

| 항목 | 내용 |
|------|------|
| **역할** | 단일 청크 번역, 자기검증, 신규 용어 후보 수집 |
| **트리거 조건** | 메인 에이전트가 청크 분할 완료 후 각 청크 파일 경로를 전달하며 호출 |
| **입력** | 청크 JSON 파일 경로 (`/output/chunks/chunk_{id}_source.json`), 분야 정보, `shared_glossary.json` 경로 |
| **출력** | `/output/chunks/chunk_{id}_translated.json` (원문, 번역문, 자기검증 결과 포함), `/output/chunks/glossary_candidates_{id}.json` (신규 전문 용어 후보) |
| **데이터 전달 방식** | 파일 기반 (청크 파일 경로를 프롬프트 인라인으로 전달) |
| **참조 스킬** | 없음 (LLM 직접 처리) |
| **AGENT.md 핵심 섹션** | 번역 품질 기준, 수식 보존 규칙, 용어집 읽기 전용 규칙, 용어 후보 출력 규칙 (`glossary_candidates_{id}.json` 포맷), 자기검증 체크리스트, 출력 JSON 스키마 |

### 3.6 주요 산출물 파일 형식

| 파일 | 형식 | 주요 필드 |
|------|------|----------|
| `pdf_meta.json` | JSON | `type` (digital/scanned), `page_count`, `layout_type` (single/double_column), `has_formulas`, `domain` |
| `layout_map.json` | JSON | 페이지별 배열: `[{page, elements: [{type, bbox, content_ref, column}]}]`. type: text/formula_inline/formula_block/code/table/asset. column: 0/1/2 |
| `assets_manifest.json` | JSON | `[{id, page, bbox, filepath, caption, type}]` (type: formula_block/code/asset) |
| `chunk_{id}_source.json` | JSON | `{id, section, page_range, elements: [{type, text, bbox, column}]}`. table 타입 element는 `cells: [[row, col, text]]` 필드 추가 |
| `chunk_{id}_translated.json` | JSON | `{id, original, translated, self_check: {passed, notes}}` |
| `translation_final.json` | JSON | 모든 청크 병합, 순서 보장 |
| `shared_glossary.json` | JSON | `[{source_term, translated_term, domain, first_seen_chunk}]` |
| `glossary_candidates_{id}.json` | JSON | `[{source_term, suggested_translation, context}]` |
| `overflow_log.json` | JSON | `[{page, bbox, truncated_text}]` |
| `error_log.json` | JSON | `[{step, error_type, message, affected_pages, timestamp, recommended_action}]` |
| `review_step4.txt` | 텍스트 | `APPROVED` 또는 누락 페이지 번호 목록 |
| `review_step8.txt` | 텍스트 | `APPROVED` 또는 `페이지\|원문일부\|수정요청` 형식 |

---

## 4. 기술 스택 권장 (구현 시 참고)

| 목적 | 권장 도구 |
|------|----------|
| PDF 파싱 (디지털) | `pdfplumber` 또는 `pymupdf (fitz)` |
| 표 추출 | `pdfplumber` (`extract_table()` 내장, 2D 배열 반환) |
| OCR (스캔본) | `pytesseract` + `pdf2image` 또는 `easyocr` |
| 이미지 crop | `pymupdf` (내장 crop 기능) |
| PDF 재조판 | `reportlab` 또는 `pymupdf` |
| 한국어 PDF 폰트 | 나눔고딕 (`NanumGothic.ttf`) 고정 |
| 코드 블록 감지 | 폰트명(Courier/Mono) + bbox 비율 기반 휴리스틱 |
| 병렬 서브에이전트 | Claude Code의 `Task` 도구 활용 |

---

## 5. 리스크 및 설계 결정 노트

| 리스크 | 대응 방식 |
|--------|----------|
| 2단 컬럼 읽기 순서 오류 | layout_map 생성 시 컬럼 감지 로직 포함, 에이전트가 결과 샘플 검수. column 필드로 순서 보정 |
| 수식 영역 오인식 (텍스트로 파싱) | formula_block 영역은 bbox 기준 crop 이미지로 처리, 번역 스킵 |
| 번역 텍스트 길이 증가로 레이아웃 오버플로우 | pdf-composer에서 폰트 크기 자동 축소 (최소 6pt) → 불가 시 속역 제거 + overflow_log.json 기록 |
| 병렬 번역 시 용어 불일치 | Step 4.5 공유 용어집 초기화 + Step 6 전체 LLM 검증 후 불일치 청크 재번역 |
| 스캔본 OCR 저품질 | 저신뢰도 페이지 로그 기록 후 human review Step 4에서 함께 확인 |
| 인라인 수식 LaTeX 원문 보존 시 PDF 폰트 미지원 | formula_inline은 원문 텍스트 그대로 배치 (LaTeX 렌더링 없음). 한계 명시: LaTeX 문법 문자가 깨질 수 있음 |
| 표 셀 병합(colspan/rowspan)으로 2D 추출 실패 | pdfplumber 추출 실패 시 해당 표를 asset 이미지로 fallback 처리 |
| 배치 모드 중 한 논문 실패 시 전체 중단 방지 | per-paper 독립 에러 핸들링. 실패 논문은 error_log.json 기록 후 다음 논문 계속 진행 |
| Step 6 전체 번역문 LLM 검증 비용 | 50 chunks 이하: 전체 검증. 50 chunks 초과: 섹션별 샘플링으로 대체 |
