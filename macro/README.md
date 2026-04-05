# macro/ — 매크로 에이전트 모듈 (Real-time Macro Nowcasting Engine)

멀티에이전트 투자 브리핑 시스템에서 **거시경제(Macro) 판독 에이전트** 역할을 담당합니다.

공공기관의 실물 경제 지표(GDP, 산업생산 등)가 가지는 1~2개월의 지연(Lag) 한계를 극복하기 위해, 매일 변동하는 고빈도(High-frequency) 금융 데이터를 활용한 **'실시간 나우캐스팅(Nowcasting)'** 기법을 적용했습니다. 

한국은행 ECOS 데이터를 수집하여 거시경제 국면(Regime)과 시스템 리스크를 분석하고 다른 에이전트에게 수학적으로 검증된 확률과 원인 분석(Attribution) 데이터를 제공합니다.

---

## 아키텍처 및 방법론 설계 철학

본 모듈은 실무와 학술 논문에 기반한 **2-Step 하이브리드 추론 엔진 (PCA + Markov Regime Switching)**을 사용합니다.

* **[1단계] 입력 데이터 선정 (4대 부문 통합 접근):** 한국 금융위기 식별에 관한 실증 논문(김성아 외, 2015)의 '금융 부문 전반 통합 접근 방식'을 차용했습니다. 논문과 1:1로 매칭되도록 은행채 스프레드(은행), 원/달러 환율(외환), KOSPI(주식), 장단기/신용/CP 스프레드(채권)를 핵심 변수로 선정하여 매일 수집합니다.
* **[2단계] 차원 축소 및 노이즈 필터링 (PCA 압축):** 일간 데이터 고유의 극심한 노이즈와 가짜 위기 경보를 걸러내기 위해 주성분 분석(PCA)을 도입했습니다. 개별 시장의 일시적 튀어오름은 버리고, 4개 시장이 동시에 무너지는 '공통된 공포 심리'만을 단일 '금융스트레스 요인(FSI)'으로 압축합니다.
* **[3단계] 실시간 국면 추론 (Markov Model):** 자의적인 임계치(Threshold)를 배제하고, 압축된 FSI를 3-State 마코프 모형에 투입합니다. 다변량 모형의 연산 에러(차원의 저주)를 막기 위해 단일 시계열 구조를 채택하여, 모델이 스스로 과거 1년 치를 롤링 학습해 당일의 위기 확률을 계산합니다.
* **[4단계] 설명 가능한 데이터 출력 (Attribution):** LLM의 환각을 막기 위해 PCA 가중치 역산 로직을 도입했습니다. 단순 확률 통보를 넘어 "오늘 위기의 주도 변수는 원/달러 환율 급등"이라는 수학적 기여도 기반의 인과관계를 JSON에 동적으로 조립하여 출력합니다.

---

## 폴더 구조

```text
macro/
├── macro_main.py                # 실행 진입점
├── macro_agents/
│   └── macro_agent.py           # 통합 오케스트레이터
├── macro_collectors/
│   ├── ecos_api.py              # 한국은행 ECOS 데이터 수집
│   └── quant_models.py          # 퀀트 모델 연산 (PCA, 마코프 국면전환, 기여도 역산)
├── utils/
│   └── logger.py                # 공통 로거
├── README.md
└── .env.example
```

---

## 파일별 역할 및 파이프라인

별도의 실행 파라미터 없이 Input -> Process -> Output 3단계를 자동 수행합니다.

### `macro_main.py` — 실행 진입점
* **역할:** `run_macro_agent()` 호출 후, 분석 결과를 레벨별(Level 1~3)로 콘솔에 출력하고 `output/macro_agent_{timestamp}.json` 형태로 저장합니다.
* **실행:** `python macro_main.py`

### `macro_collectors/ecos_api.py` — 데이터 수집 (Input)
* **데이터 소스:** 한국은행 ECOS OpenAPI (`ECOS_API_KEY` 필수)
* **Input:** `get_macro_raw_data()`
* **Output:** `pandas.DataFrame` (KOSPI, USD_KRW, Bond_3Y, Bond_10Y, Corp_3Y, Bank_Bond 결측치 보정 병합본)

### `macro_collectors/quant_models.py` — 퀀트 모델 연산 (Process)
* **데이터 소스:** `ecos_api.py`에서 전달받은 DataFrame
* **Input:** `run_macro_quant_pipeline(df_merged)`
* **Output:** 전처리된 데이터에서 PCA를 통해 단일 금융스트레스지수(FSI) 요인을 추출하고, 이를 3-State 마코프 국면전환 모형(Markov Regime-Switching Model)에 투입 및 가중치 역산(Attribution)을 수행하여 도출된 국면 확률 JSON 구조체를 반환합니다.

### `macro_agents/macro_agent.py` — 통합 오케스트레이터 (Output)
수집 모듈과 연산 모듈을 순차 호출하며, 완성된 페이로드는 다른 에이전트의 필드 입력값으로 전달됩니다. 출력 구조는 아래의 3. 출력 (Output Payload)에 자세히 설명되어있습니다.

---

## 통합 데이터 파이프라인 및 I/O



### 1. 입력 (Input Data)
실행 시점을 기준으로 한국은행 ECOS API를 호출하여 과거 1년 치의 핵심 일간 지표를 수집합니다. (KOSPI, 원/달러 환율, 장단기 금리차, 신용/CP 스프레드, 은행채 스프레드)

### 2. 연산 (Process)
* **정제:** 휴장일이 다른 각 시장 데이터를 병합(Outer Join, Forward Fill)하고 표준화(StandardScaler) 진행.
* **압축:** PCA를 통해 다중 지표를 단일 시계열(FSI)로 통합.
* **추론:** 3-State 마코프 모형에 투입하여 실시간 국면 확률 추정.
* **해석:** PCA 가중치를 역산하여 당일 스트레스 폭등을 주도한 핵심 변수 추출.

### 3. 출력 (Output Payload)
다른 에이전트가 참고할 보고서를 생성합니다.

```json
{
  "meta": {
    "as_of": "2026-04-01 15:30",
    "base_models": ["3-State Univariate Markov", "PCA-based FSI", "PCA Attribution"]
  },
  "raw_indicators": {
    "market_index": {
      "KOSPI": {"current": 5277.3, "dod_change_pct": -1.2, "interpretation": "하락"},
      "USD_KRW": {"current": 1530.5, "dod_change_pct": 1.13}
    },
    "interest_rates_spread": {
      "Term_Spread": {"current": 0.327, "wow_change_pt": 0.015, "status": "정상"},
      "Credit_Spread": {"current": 0.641, "wow_change_pt": 0.041}
    }
  },
  "quantitative_models": {
    "fsi_factor_score": 2.145,
    "regime_probabilities": {
      "state_0_normal": 0.021, "state_1_caution": 0.056, "state_2_crisis": 0.923
    }
  },
  "objective_analysis": {
    "current_regime_diagnosis": "현재 한국 경기 국면은 위기/위험 (Crisis) 상태이며, 해당 국면 진입 확률이 92.3%로 지배적임. 마코프 모형 분석 결과, 원/달러 환율 급등과 신용 스프레드 확대가 현재 시스템 리스크를 견인하는 핵심 요인으로 판별됨.",
    "risk_assessment": "투자 환경 위험도는 High 수준. 스트레스 지수 상승의 1위 기여 요인인 원/달러 환율이 급격히 악화되며 전체 변동성을 키우고 있음.",
    "momentum": "위험 가속 (전일 대비 금융 스트레스 요인 수치 상승)"
  },
  "errors": []
}
```

---

## 환경 설정 및 실행

`.env.example`을 복사하여 `.env`를 생성하고 ECOS API 키를 입력합니다.

```bash
# 1. 가상환경 세팅 및 패키지 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt

# 2. 에이전트 실행
python macro_main.py
```

---

## 현재 개발 상태 (Implementation Status)

**[ 구현 완료]**
* **데이터 수집 (ecos_api.py):** 한국은행 ECOS OpenAPI 연동 및 4대 부문 핵심 지표 일간 데이터 수집 및 전처리 파이프라인.
* **퀀트 연산 (quant_models.py):** StandardScaler 및 scikit-learn PCA를 활용한 금융스트레스지수(FSI) 차원 축소.
* **국면 추론 엔진:** statsmodels 기반 3-State 단일 시계열 마코프 국면전환 모형(Markov Regime-Switching) 롤링 연산.


**[ 미구현 / 향후 과제]**
* **XAI 기반 페이로드 조립:** PCA 가중치 역산을 통한 위험 요인 기여도 텍스트 생성 및 JSON Output 규격화.
* **아웃오브샘플(Out-of-sample) 백테스트:** 코로나19, 레고랜드 사태 등 과거 특정 위기 구간에 대한 백테스트 모듈 구축 후 다양한 입력데이터 조합, 확률 민감도(Threshold) 최적화 튜닝.

---

## 참고 문헌 및 아키텍처 설계 근거 (References)

본 에이전트는 자의적인 구성이 아닌, 다음의 학술 연구들을 뼈대로 설계되었습니다.

* **입력 데이터 4대 부문 선정:** *김성아, 박수남, 김영재. (2015). "금융위기 식별을 위한 최적 금융스트레스지수."* (특정 부문만의 한계를 극복하기 위해 한국 금융시장을 은행, 외환, 주식, 채권으로 나누어 통합 접근하는 방식과 각 핵심 지표를 1:1 차용)
* **금리차 지표의 경기 선행성:** *Estrella, A., & Mishkin, F. S. (1998).* (장단기 금리차가 실물 경기 침체를 선행하는 핵심 프록시 지표임을 증명)
* **PCA 기반의 다변량 노이즈 필터링:** *Hakkio, C. S., & Keeton, W. R. (2009).* (개별 변수의 엇갈리는 노이즈를 제어하고 시스템적 공통 요인을 추출하기 위해 PCA를 활용하는 논리 차용)
* **실시간 국면전환 (Regime-Switching) 추론:** *Hamilton, J. D. (1989) & Chauvet, M. (1998).* (고정된 임계치 없이 시계열 이면에 숨겨진 국면을 확률적으로 추정하는 2-Step 동적 요인 모형 구조)
* **단일 시계열 마코프 모형의 시스템 안정성:** *Guidolin, M. (2011).* (다변량 마코프 모형이 실시간 무인 연산에서 일으키는 '차원의 저주' 한계를 방어하고, 단일 시계열(Univariate) 3-State 모형을 통한 최적화 수렴 보장 논리 제공)
```
