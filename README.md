# 📄 논문 번역 시스템

영문·일본어 학술 논문 PDF를 한국어로 번역하여 PDF로 저장하는 웹 애플리케이션입니다.

---

## 주요 기능

- **드래그 앤 드롭 업로드** — PDF 파일을 끌어다 놓거나 파일 탐색기로 선택
- **언어 자동 감지** — 영어(🇺🇸) / 일본어(🇯🇵) 자동 판별 후 언어별 최적 번역
- **번역 실행 버튼** — 업로드 후 내용 확인 → 버튼 클릭 시 번역 시작
- **실시간 진행 상황** — 청크 단위 번역 진행률 및 단계 표시
- **번역 취소** — 번역 중 언제든 취소 가능
- **PDF 뷰어** — 브라우저 내에서 번역본 / 원본 토글 보기
- **다운로드** — 번역 완료 PDF 즉시 다운로드
- **히스토리** — 모든 번역 작업 내역을 사이드바에 영구 보관

---

## 시스템 구성

```
Document-Translate/
├── web/                        # 웹 애플리케이션
│   ├── app.py                  # FastAPI 백엔드
│   ├── requirements.txt        # 패키지 목록
│   ├── start.bat               # Windows 실행 스크립트
│   └── static/
│       └── index.html          # 프론트엔드 SPA
└── paper-translation/          # CLI 번역 파이프라인 (Claude Code)
    ├── CLAUDE.md               # 오케스트레이터 지침
    ├── requirements.txt
    ├── docs/
    │   └── domain_glossary.md  # 분야별 전문 용어집
    ├── fonts/                  # 폰트 안내
    ├── scripts/
    │   └── md_to_pdf.py        # 마크다운 → PDF 변환
    └── .claude/
        ├── agents/             # 번역 서브에이전트
        └── skills/             # PDF 파싱·추출·조판 스킬
```

---

## 설치 및 실행

### 사전 요구사항

| 항목 | 내용 |
|------|------|
| Python | 3.11 이상 |
| 폰트 | NanumGothic (`C:\Windows\Fonts\NanumGothic.ttf`) |
| API 키 | [Anthropic Console](https://console.anthropic.com/settings/keys)에서 발급 |

NanumGothic 폰트가 없으면 [네이버 나눔폰트](https://hangeul.naver.com/font)에서 설치하세요.

### 패키지 설치

```bash
pip install -r web/requirements.txt
```

### 서버 실행

**Windows — start.bat 사용 (권장)**

```bat
set ANTHROPIC_API_KEY=sk-ant-api03-...
cd web
start.bat
```

**직접 실행**

```bash
set ANTHROPIC_API_KEY=sk-ant-api03-...
cd web
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000` 접속

---

## 번역 파이프라인

```
PDF 업로드
    ↓
언어 감지 (영어 / 일본어)          ← 첫 5페이지 샘플링
    ↓
페이지별 텍스트 추출               ← pdfplumber
    ↓
~4,000자 단위 청크 분할
    ↓
Claude API 한국어 번역             ← claude-sonnet-4-6
    ↓
translation_ko.md 생성
    ↓
Markdown → PDF                    ← reportlab + NanumGothic
```

### 지원 언어

| 언어 | 감지 방식 | 특화 번역 규칙 |
|------|-----------|----------------|
| 🇺🇸 영어 | 히라가나·한자 비율 5% 미만 | 저자명·기관명·모델명 원문 유지 |
| 🇯🇵 일본어 | 히라가나·한자 비율 5% 이상 | です·ます체 → 한국어 학술 문체 |

### 파일명으로 분야 지정 (선택)

파일명 앞에 도메인 접두사를 붙이면 분야별 전문 용어를 우선 적용합니다.

```
cs_attention_is_all_you_need.pdf
physics_quantum_computing.pdf
medicine_clinical_trial.pdf
```

| 접두사 | 분야 |
|--------|------|
| `cs` | 컴퓨터과학 / AI / ML |
| `physics` | 물리학 |
| `chemistry` | 화학 |
| `medicine` | 의학 |
| `biology` | 생물학 |
| `economics` | 경제학 |

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/upload` | PDF 업로드 (언어 감지 포함) |
| `POST` | `/api/jobs/{id}/start` | 번역 실행 |
| `POST` | `/api/jobs/{id}/cancel` | 번역 취소 |
| `GET`  | `/api/jobs` | 전체 히스토리 조회 |
| `GET`  | `/api/jobs/{id}` | 특정 Job 상태 조회 |
| `GET`  | `/api/jobs/{id}/view-translated` | 번역본 PDF 보기 |
| `GET`  | `/api/jobs/{id}/view-original` | 원본 PDF 보기 |
| `GET`  | `/api/jobs/{id}/download` | 번역본 PDF 다운로드 |

---

## 주의사항

- 스캔 이미지 PDF(텍스트 레이어 없음)는 번역이 불가합니다.
- 번역 취소 시 현재 처리 중인 청크가 완료된 후 중단됩니다.
- `paper-translation/input/`, `paper-translation/output/`, `web/jobs.json`은 `.gitignore`로 제외됩니다.
