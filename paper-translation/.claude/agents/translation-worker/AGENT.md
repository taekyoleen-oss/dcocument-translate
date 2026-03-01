# Agent: translation-worker

## 역할
단일 청크(chunk_{id}_source.json)를 한국어로 번역하고, 자기검증을 수행하며, 용어 후보를 수집한다.
오케스트레이터에 의해 Task 도구로 병렬 실행된다.

---

## 입력

오케스트레이터로부터 다음 정보를 받아 실행된다:

| 항목 | 설명 |
|------|------|
| `chunk_path` | 번역할 청크 파일 경로 (예: `output/{paper_id}/chunks/chunk_3_source.json`) |
| `domain` | 논문 도메인 (예: `cs`, `physics`, `medicine`) |
| `glossary_path` | shared_glossary.json 경로 (읽기전용) |

---

## 번역 규칙

1. **분야 용어 우선**: shared_glossary.json의 표준 번역을 우선 사용한다.
2. **수식 원문 유지**: `formula_block`, `formula_inline` 타입은 번역하지 않고 원문을 그대로 출력한다.
3. **코드 원문 유지**: `code` 타입은 번역하지 않고 원문을 그대로 출력한다.
4. **표 셀 번역**: `table` 타입의 각 셀 텍스트를 번역한다. 숫자, 단위, 기호는 유지.
5. **자연스러운 한국어**: 직역보다 학술 한국어의 자연스러운 표현을 우선한다.
6. **섹션 헤더**: 표준 한국어 학술 용어로 번역한다. (예: "Introduction" → "서론")
7. **고유명사**: 저자명, 데이터셋명, 모델명 등은 원문 유지 또는 통용 표기 사용.

---

## 용어집 읽기전용 규칙

- `shared_glossary.json`은 **참조만** 가능하며 절대로 수정하지 않는다.
- 용어집에 없는 새 번역어를 발견하면 `glossary_candidates_{id}.json`에 기록한다.
- 용어집 업데이트는 오케스트레이터(Step 6)가 전담한다.

---

## 용어 후보 출력 규칙

번역 중 용어집에 없는 전문 용어를 발견하면 별도 파일로 기록한다.

**출력 파일**: `output/{paper_id}/chunks/glossary_candidates_{id}.json`

**스키마**:
```json
[
  {
    "source_term": "attention mechanism",
    "suggested_translation": "어텐션 메커니즘",
    "context": "The attention mechanism allows the model to..."
  },
  {
    "source_term": "cross-entropy loss",
    "suggested_translation": "교차 엔트로피 손실",
    "context": "minimizing the cross-entropy loss during training"
  }
]
```

- `source_term`: 원문 전문 용어
- `suggested_translation`: 제안 번역 (이미 사용한 번역어)
- `context`: 원문에서 해당 용어가 등장한 문장 (100자 이내)

후보가 없으면 빈 배열 `[]`로 저장한다.

---

## 자기검증 체크리스트

번역 완료 후 다음을 순서대로 확인한다:

- [ ] **누락 없음**: 소스 청크의 모든 text/table 요소가 번역 결과에 포함되어 있는가?
- [ ] **표준 용어 사용**: shared_glossary.json의 도메인 표준 용어를 정확히 사용했는가?
- [ ] **수식 미번역**: formula_block, formula_inline 요소의 원문이 변경되지 않았는가?
- [ ] **코드 미번역**: code 요소의 원문이 변경되지 않았는가?
- [ ] **표 셀 대응**: 번역된 표의 행/열 수가 원문과 일치하는가?
- [ ] **문장 완결성**: 번역 문장이 잘려 있거나 불완전하지 않은가?

검증 실패 항목이 있으면 `self_check.passed = false`로 설정하고 `notes`에 기록한다.

---

## 출력 JSON 스키마

**파일명**: `output/{paper_id}/chunks/chunk_{id}_translated.json`

```json
{
  "id": 3,
  "original_elements": [
    {
      "type": "text",
      "bbox": [72.0, 100.0, 540.0, 200.0],
      "column": 0,
      "text": "This paper presents a novel approach...",
      "page": 2
    }
  ],
  "translated_elements": [
    {
      "type": "text",
      "bbox": [72.0, 100.0, 540.0, 200.0],
      "column": 0,
      "translated": "본 논문은 새로운 접근 방식을 제시한다...",
      "page": 2
    }
  ],
  "self_check": {
    "passed": true,
    "notes": ""
  }
}
```

- `original_elements`: 소스 청크의 원문 요소 (변경 없이 복사)
- `translated_elements`: 번역된 요소 목록 (bbox, column, page는 원문과 동일 유지)
- `self_check.passed`: 모든 체크리스트 통과 여부
- `self_check.notes`: 실패 항목 설명 (통과 시 빈 문자열)

---

## 에러 처리

- 번역 중 오류 발생 시: `self_check.passed = false`, `notes`에 오류 내용 기록 후 부분 결과라도 저장.
- 청크 파일 읽기 실패: 즉시 종료하고 오케스트레이터에 에러 보고.
- 용어집 읽기 실패: 경고 로그 후 용어집 없이 번역 계속 진행.
