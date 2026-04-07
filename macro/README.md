# macro/ — 매크로 에이전트 모듈 (Real-time Macro Nowcasting Engine)

멀티에이전트 투자 브리핑 시스템 및 AI 해설 대시보드에서 **거시경제(Macro) 판독 에이전트** 역할을 담당합니다.

공공기관의 실물 경제 지표(GDP, 산업생산 등)가 가지는 1~2개월의 지연(Lag) 한계를 극복하기 위해, 매일 변동하는 고빈도(High-frequency) 금융 데이터를 활용한 **'실시간 나우캐스팅(Nowcasting)'** 기법을 적용했습니다. 

한국은행 ECOS 데이터를 수집하여 거시경제 국면(Regime)과 시스템 리스크를 분석하고 다른 에이전트에게 수학적으로 검증된 확률과 원인 분석(Attribution) 데이터를 제공합니다.

---

## 🏛 아키텍처 설계 철학 및 학술적 근거 (Architecture & Academic Basis)

본 모듈은 단순한 지표의 단순 평균이나 조건문(If-else)이 아닌, 글로벌 퀀트 실무와 학술 논문에 1:1로 매칭되는 **2-Step 하이브리드 추론 엔진 (PCA + Markov Regime Switching)**을 가동합니다. 각 파이프라인 단계별 적용된 아키텍처와 그 학술적 근거는 다음과 같습니다.

### [1단계] 입력 데이터 선정 (4대 부문 통합 접근)
* **적용 아키텍처:** 적용 아키텍처: 은행 부문(은행채 스프레드), 외환 부문(원/달러 환율), 주식 부문(KOSPI), 채권 부문(장단기 금리차, 신용 스프레드, CP 스프레드) 등 총 4개 금융 시장을 아우르는 지표를 핵심 변수로 매일 수집합니다.
* **학술적 근거 1:** *김성아, 박수남, 김영재 (2015). "금융위기 식별을 위한 최적 금융스트레스지수."* 👉 특정 부문만의 한계를 극복하기 위해 한국 금융시장을 4대 부문(은행, 외환, 주식, 채권)으로 나누어 통합 접근하는 방식을 채택하고, 해당 논문에서 검증된 핵심 지표를 그대로 차용했습니다.
* **학술적 근거 2:** *Estrella, A., & Mishkin, F. S. (1998).* 👉 장단기 금리차가 실물 경기 침체를 선행하는 핵심 프록시 지표임을 증명한 연구를 바탕으로 채권 부문 데이터의 타당성을 확보했습니다.

### [2단계] 차원 축소 및 노이즈 필터링 (PCA 압축)
* **적용 아키텍처:** 일간 데이터 고유의 극심한 노이즈와 가짜 위기 경보를 걸러내기 위해 주성분 분석(PCA)을 도입했습니다. 4개 시장이 동시에 무너지는 '공통된 공포 심리'만을 단일 '금융스트레스 요인(FSI)'으로 압축합니다.
* **학술적 근거:** *Hakkio, C. S., & Keeton, W. R. (2009).* 👉 미국 캔자스시티 연준(KCFSI)이 개별 변수의 엇갈리는 노이즈를 제어하고 시스템적 공통 요인(Co-movement)을 추출하기 위해 PCA를 활용한 논리를 벤치마킹했습니다.

### [3단계] 실시간 국면 추론 (Markov Model)
* **적용 아키텍처:** 자의적인 임계치(Threshold)를 배제하고, 압축된 단일 FSI 시계열을 3-State 마코프 모형에 투입합니다. 모델이 스스로 과거 1년 치를 롤링 학습해 당일의 위기 확률을 계산합니다.
* **학술적 근거 1:** *Hamilton, J. D. (1989) & Chauvet, M. (1998).* 👉 고정된 임계치 없이 시계열 이면에 숨겨진 국면을 확률적으로 추정하는 2-Step 동적 요인 모형 구조를 차용했습니다.
* **학술적 근거 2:** *Guidolin, M. (2011).* 👉 다변량 마코프 모형이 실시간 무인 연산에서 일으키는 '차원의 저주(Curse of Dimensionality)' 한계를 방어하고, 단일 시계열(Univariate) 3-State 모형을 통한 최적화 수렴 보장의 논리를 제공받았습니다.

### [4단계] 설명 가능한 데이터 출력 (Attribution)
* **적용 아키텍처:** LLM의 환각을 막기 위해 PCA 가중치 역산 로직을 도입했습니다. 단순 확률 통보를 넘어 "오늘 위기의 주도 변수는 원/달러 환율 급등"이라는 수학적 기여도 기반의 인과관계를 JSON에 동적으로 조립하여 출력합니다.

---

## 📂 폴더 구조

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

## ⚙️ 파일별 역할 및 파이프라인

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

## 🔄 통합 데이터 파이프라인 및 I/O

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
    "stock_market": {
      "KOSPI": {"current": 5277.3, "dod_change_pct": -1.2, "interpretation": "하락"}
    },
    "fx_market": {
      "USD_KRW": {"current": 1530.5, "dod_change_pct": 1.13}
    },
    "bond_market": {
      "Term_Spread": {"current": 0.327, "wow_change_pt": 0.015, "status": "정상"},
      "Credit_Spread": {"current": 0.641, "wow_change_pt": 0.041},
      "CP_Spread": {"current": 1.250, "wow_change_pt": 0.082} 
    },
    "banking_sector": {
      "Bank_Bond_Spread": {"current": 0.452, "wow_change_pt": 0.021}
    }
  },
  "quantitative_models": {
    "fsi_factor_score": 2.145,
    "regime_probabilities": {
      "state_0_normal": 0.021, "state_1_caution": 0.056, "state_2_crisis": 0.923
    }
  },
  "objective_analysis": {
    "current_regime_diagnosis": "현재 한국 경기 국면은 위기/위험 (Crisis) 상태이며, 해당 국면 진입 확률이 92.3%로 지배적임. 마코프 모형 분석 결과, 원/달러 환율 급등과 은행채 스프레드 확대가 현재 시스템 리스크를 견인하는 핵심 요인으로 판별됨.",
    "risk_assessment": "투자 환경 위험도는 High 수준. 스트레스 지수 상승의 1위 기여 요인인 원/달러 환율이 급격히 악화되며 전체 변동성을 키우고 있음.",
    "momentum": "위험 가속 (전일 대비 금융 스트레스 요인 수치 상승)"
  },
  "errors": []
}
```

---

## 🛠️ 환경 설정 및 실행

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

## 🚦 현재 개발 상태 (Implementation Status)

**[✅ 구현 완료]**
* **데이터 수집 (ecos_api.py):** 한국은행 ECOS OpenAPI 연동 및 4대 부문 핵심 지표 일간 데이터 수집 및 전처리 파이프라인.
* **퀀트 연산 (quant_models.py):** StandardScaler 및 scikit-learn PCA를 활용한 금융스트레스지수(FSI) 차원 축소.
* **국면 추론 엔진:** statsmodels 기반 3-State 단일 시계열 마코프 국면전환 모형(Markov Regime-Switching) 롤링 연산.

**[🚧 미구현 / 향후 과제]**
* **XAI 기반 페이로드 조립:** PCA 가중치 역산을 통한 위험 요인 기여도 텍스트 생성 및 JSON Output 규격화.
* **아웃오브샘플(Out-of-sample) 백테스트:** 코로나19, 레고랜드 사태 등 과거 특정 위기 구간에 대한 백테스트 모듈 구축 후 다양한 입력데이터 조합, 확률 민감도(Threshold) 최적화 튜닝.
