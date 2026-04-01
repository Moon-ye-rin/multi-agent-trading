# macro/ — 매크로 에이전트 모듈

멀티에이전트 투자 브리핑 시스템에서 **매크로 에이전트** 역할을 담당합니다.
한국은행 ECOS 데이터를 수집하여 거시경제 국면(Regime)과 투자 환경 위험도를 분석하고,
불/베어 에이전트 및 오케스트레이터에게 전달할 정형 페이로드를 생성합니다.

---

## 폴더 구조

```text
macro/
├── macro_main.py                # 실행 진입점
├── macro_agents/
│   └── macro_agent.py           # 통합 오케스트레이터
├── macro_collectors/
│   ├── ecos_api.py              # 한국은행 ECOS 데이터 수집
│   └── quant_models.py          # 퀀트 모델 연산 (PCA, 마코프 국면전환)
├── utils/
│   └── logger.py                # 공통 로거
├── README.md
└── .env.example
```

---

## 데이터 흐름

```text
macro_main.py
    └─▶ run_macro_agent()
            ├── [1/2] ecos_api.py        → 4대 핵심 지표 수집 및 병합 (DataFrame)
            ├── [2/2] quant_models.py    → PCA 추출 및 마코프 확률 연산 (JSON 구조화)
                                         ↓
                            콘솔 출력 + JSON 저장 (output/)
```

---

## 파일별 역할 및 I/O

### `macro_main.py` — 실행 진입점

실행 방법:
```bash
python macro_main.py
```
**역할:** `run_macro_agent()` 호출 후, 분석 결과를 레벨별(Level 1~3)로 콘솔에 출력하고 `output/macro_agent_{timestamp}.json` 형태로 저장합니다.

---

### `macro_agents/macro_agent.py` — 통합 오케스트레이터

**Input:** 별도 파라미터 없음 (실행 시점의 실시간 데이터 자동 수집)

**Output (페이로드 구조):**
{
  "meta": {
    "as_of": "2026-03-31 15:30", // 리포트가 생성된 기준 시각
    "base_models": [ // 분석에 사용된 핵심 알고리즘 및 퀀트 모형
      "3-State Markov Regime Switching",
      "PCA-based FSI"
    ]
  },
  "raw_indicators": { // 한국은행 ECOS API에서 수집한 날것의 원천 거시 지표
    "market_index": {
      "KOSPI": {
        "current": 5277.3, // KOSPI 현재 지수
        "dod_change_pct": 0.0, // 전일 대비 등락률(%)
        "interpretation": "하락" // 등락률 기반 단순 해석 (상승/하락)
      },
      "USD_KRW": {
        "current": 1513.4, // 원/미국달러 매매기준율
        "dod_change_pct": 0.35 // 전일 대비 환율 변동률(%)
      }
    },
    "interest_rates_spread": {
      "Term_Spread": {
        "current": 0.327, // 장단기 금리차 (국고채 10년물 - 3년물, 단위: %p)
        "wow_change_pt": 0.015, // 전주 대비 변동폭(%p)
        "status": "정상" // 양수면 정상, 음수면 경기 침체 전조인 역전으로 판별
      },
      "Credit_Spread": {
        "current": 0.614, // 신용 스프레드 (우량회사채 AA- - 국고채 3년물, 단위: %p)
        "wow_change_pt": 0.016 // 전주 대비 변동폭(%p). 급등 시 기업의 자금 조달 경색 의미
      }
    }
  },
  "quantitative_models": { // 원천 데이터를 통계 모형에 통과시킨 퀀트 연산 결과값
    "fsi_factor_score": -0.6779, // 4개 지표를 주성분 분석(PCA)으로 압축한 단일 금융스트레스지수(FSI) 점수
    "regime_probabilities": { // FSI 점수를 3국면 마코프 모형에 넣어 도출한 실시간 국면 확률 (세 국면 합계 1.0)
      "state_0_normal": 0.7849, // 경제가 정상/안정 국면일 확률 (78.49%)
      "state_1_caution": 0.1518, // 경제가 경계/둔화 국면일 확률 (15.18%)
      "state_2_crisis": 0.0633 // 경제가 위기/위험 국면일 확률 (6.33%)
    }
  },
  "objective_analysis": { // 오케스트레이터(LLM)가 읽기 쉽도록 확률 데이터를 텍스트로 가공한 객관적 요약
    "current_regime_diagnosis": "현재 한국 경기 국면은 정상/안정 (Normal) 상태이며, 해당 국면 진입 확률이 78.5%로 지배적임.", // 가장 확률이 높은 국면 판정 결과
    "risk_assessment": "투자 환경 위험도는 Low 수준. 장단기 금리차가 0.327%p를 기록하고 있음.", // 확률 기반 위험도 등급(Low/Medium/High) 및 핵심 지표 동향 요약
    "momentum": "위축" // 전일 FSI 점수와 비교한 시장 스트레스 모멘텀 방향 (개선/위축)
  },
  "errors": [] // 파이프라인 구동 중 발생한 예외 상황(API 호출 실패, 결측치 등) 메시지 목록 (정상 구동 시 빈 배열)
}
수집 모듈과 연산 모듈을 순차 호출하며, 완성된 페이로드는 불/베어 에이전트의 `macro` 필드 입력값으로 전달됩니다.

---

### `macro_collectors/ecos_api.py` — 데이터 수집

**데이터 소스:** 한국은행 ECOS OpenAPI (`ECOS_API_KEY` 필수)

**Input:** `get_macro_raw_data()`

**Output:** `pandas.DataFrame` (KOSPI, USD_KRW, Bond_3Y, Bond_10Y, Corp_3Y 결측치 보정 병합본)

---

### `macro_collectors/quant_models.py` — 퀀트 모델 연산

**데이터 소스:** `ecos_api.py`에서 전달받은 DataFrame

**Input:** `run_macro_quant_pipeline(df_merged)`

**Output:** 전처리된 데이터에서 PCA를 통해 단일 금융스트레스지수(FSI) 요인을 추출하고, 이를 3-State 마코프 국면전환 모형(Markov Regime-Switching Model)에 투입하여 도출된 국면 확률(정상/경계/위험) JSON 구조체를 반환합니다.
'''
---

## 환경 설정

`.env.example`을 복사하여 `.env`를 생성합니다.

```bash
cp .env.example .env
```

| 환경변수 | 필수 여부 | 설명 |
|---|---|---|
| `ECOS_API_KEY` | 필수 | 한국은행 ECOS 오픈 API 인증키 |
| `OUTPUT_DIR` | 선택 | JSON 저장 경로 (기본값: `output`) |
| `SAVE_JSON` | 선택 | JSON 저장 여부 (기본값: `true`) |
| `LOG_LEVEL` | 선택 | 로그 레벨 (기본값: `INFO`) |

---

## 설치 및 실행

시스템 파이썬 패키지 충돌(PEP 668)을 방지하기 위해 **가상환경(Virtual Environment)** 세팅 후 실행하는 것을 권장합니다.

```bash
# 1. 가상환경 생성 및 활성화 (리눅스/맥 기준)
python3 -m venv .venv
source .venv/bin/activate
# 윈도우의 경우: .venv\Scripts\activate

# 2. 패키지 설치 (루트 디렉토리의 공통 requirements.txt 참조)
pip install -r ../requirements.txt

# 3. 매크로 에이전트 실행
python macro_main.py

---

## 현재 개발 상태

| 모듈 | 상태 | 비고 |
|---|---|---|
| `ecos_api.py` | 완성 | 한국은행 공식 통계표 100% 의존  |
| `quant_models.py` | 완성 | scikit-learn(PCA), statsmodels(마코프) 기반 |
| LLM 분석 (오케스트레이터) | 미구현 | 페이로드 생성까지만 완료, 텍스트 생성은 상위 에이전트 위임 |
