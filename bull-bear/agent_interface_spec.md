# 에이전트 간 데이터 전달 인터페이스 스펙 (Phase 0)

> **목적**: 각 에이전트가 무엇을 출력하고, 불/베어 에이전트가 무엇을 입력받는지 확정.
> 구현 전 이 스펙을 고정하여, 에이전트 간 데이터 계약을 명확히 한다.
>
> **범위**: 매크로 → 불/베어, 섹터종목 → 불/베어, 시장심리 → 불/베어, 불/베어 → 오케스트레이터
>
> **설계 원칙**: 불/베어 에이전트는 동일한 패키지를 받는다. 해석 프레임(낙관 vs 비관)만 시스템 프롬프트로 분리한다.

---

## 1. 매크로 에이전트 출력 스펙

**역할**: 글로벌·국내 거시경제 지표를 수집하고 투자 국면을 판단한다.

**데이터 소스**: FRED API (`fredapi`), `yfinance` (WTI), 한국은행 ECOS API (`requests`)

**수집 지표**: 미국 기준금리, 실업률, 장단기 금리차(T10Y2Y), WTI 원유, 원/달러 환율, 한국 수출액

**분석 프레임**: 메릴린치 투자 시계 (성장 × 물가 축 → 4국면 판별)

### 출력 JSON

```json
{
  "macro_regime": "스태그플레이션",
  "regime_reason": "실업률 4.4% 경직 + 유가 92달러 급등으로 경기둔화와 물가상승 공존",
  "bull_ammunition": [
    "기준금리 3.64%로 하향 안정화, 금융비용 부담 완화",
    "장단기 금리차 0.49%p 양수 유지, 급격한 침체 신호 부재"
  ],
  "bear_ammunition": [
    "WTI 92.94달러 급등, 비용 인상 인플레이션 압력 강화",
    "원/달러 1,495원 상승, 외국인 자본 유출 우려 증대"
  ],
  "key_risk": "유가 급등발 수입 물가 충격",
  "macro_score": -0.6
}
```

### 전달 방식 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `bull_ammunition` / `bear_ammunition` | **배열(Array)** 유지 | 불/베어 에이전트가 각자의 논거 목록으로 바로 주입 가능 |
| `macro_score` | **-1.0 ~ +1.0 float** | 오케스트레이터의 `agreement_score` 계산 시 가중치 입력용 |
| 추세 문자열 포함 여부 | **미포함** (불/베어에 전달 시) | raw 추세 데이터는 매크로 에이전트 내부 분석용. 전달 객체는 결론만. |

> ⏳ **미결 — 팀 논의 필요**: `bull_ammunition` / `bear_ammunition` 필드 유지 여부
>
> - **A안 (현행 유지)**: 매크로 에이전트가 LLM으로 국면 판단 시 논거까지 동시 생성. 불/베어는 받은 논거를 프레임에 맞게 사용.
> - **B안 (지표만 전달)**: 매크로 에이전트는 지표 + regime만 출력. 불/베어가 원본 지표를 직접 해석해 논거 생성. 역할 분리가 명확하나 불/베어 프롬프트 복잡도 증가.

---

## 2. 섹터종목 에이전트 출력 스펙

**역할**: 종목의 수급·실적·섹터 흐름·밸류에이션을 수집하고 정량 데이터를 구조화한다.

**데이터 소스**: `pykrx` (수급, 섹터ETF, 밸류에이션), DART API (재무제표), 네이버/한경 크롤링 (목표주가)

### 출력 JSON

```json
{
  "ticker": "005930",
  "name": "삼성전자",
  "date": "2026-03-31",

  "supply_demand": {
    "foreign_net_20d": -214481.8,
    "foreign_net_60d": -333075.3,
    "foreign_net_120d": -262595.7,
    "foreign_consecutive_sell_5d": 5,
    "institution_net_5d": -24227.0,
    "institution_trend": "매도우위",
    "short_mid_direction_match": true,
    "sell_intensity": "심화"
  },

  "earnings": {
    "latest_quarter": "2025_3Q",
    "quarters": [
      {"period": "2025_3Q", "op_income": 121660.6, "revenue": 860617.5},
      {"period": "2025_2Q", "op_income": 46760.6,  "revenue": 745663.2},
      {"period": "2025_1Q", "op_income": 66852.7,  "revenue": 791405.0},
      {"period": "2024_3Q", "op_income": 91833.7,  "revenue": 790987.3}
    ],
    "op_income_yoy": 0.325,
    "revenue_yoy": 0.088,
    "op_income_qoq": 1.602,
    "earnings_trend_3q": "혼조"
  },

  "analyst_opinion": {
    "avg_target_price": null,
    "target_price_gap_rate": null,
    "target_price_trend": "N/A",
    "buy_ratio": null,
    "source": "naver_crawl",
    "note": "크롤링 실패 시 DART 공시 목표주가로 대체 시도. 대체도 실패 시 null 처리 후 논거 생략"
  },

  "sector_relative_strength": {
    "sector_etf": "091160",
    "rs_1m_vs_sector": -1.2,
    "rs_3m_vs_sector": -7.3,
    "rs_6m_vs_sector": 5.3,
    "rs_1y_vs_sector": -0.4,
    "rs_trend": "지속 약화",
    "diagnosis": "종목 고유 약세 (섹터는 선방)",
    "peak_rs_period": "6m"
  },

  "valuation": {
    "per": 36.38,
    "pbr": 3.11,
    "eps": 4950.0,
    "bps": 57951.0,
    "per_3y_percentile": 89.0,
    "pbr_3y_percentile": 97.0,
    "per_label": "고평가",
    "pbr_label": "고평가",
    "eps_trend": "개선 (YoY)",
    "eps_yoy_change": 1.323
  },

}
```

### 전달 방식 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 수급 데이터 단위 | **누적 순매수(억원)** 전달, 일별 배열 미전달 | 불/베어 에이전트는 흐름의 방향과 강도가 필요하지 일별 raw 데이터가 필요하지 않음. 토큰 절약. |
| 수급 기간 | 20일/60일/120일 **3구간 누적** 유지 | 단기·중기·장기 방향 불일치 여부를 에이전트가 논거로 사용 가능 |
| 실적 데이터 | **최근 4분기 절대값 + YoY/QoQ 변화율** | Bull은 QoQ 반등을, Bear는 혼조·고평가를 논거로 사용 |
| 목표주가 데이터 | **수집 실패 시 null + note 필드** | 크롤링 불안정성 대응. 에이전트가 null 체크 후 논거 생략 처리 |

---

## 3. 시장심리 에이전트 출력 스펙

**역할**: V-KOSPI, 외국인 수급, KOSPI 변화율을 종합하여 시장 심리 상태를 점수화한다.

**데이터 소스**: `yfinance` (V-KOSPI `^KSVIX`, KOSPI `^KS11`), `pykrx` (외국인 수급)

**스코어링**: V-KOSPI 40% + 외국인수급 40% + KOSPI변화 20% 가중합

### 출력 JSON

```json
{
  "sentiment_label": "낙관",
  "sentiment_score": 0.67,
  "vkospi": {
    "value": 18.2,
    "change_weekly": -2.3
  },
  "foreign_flow": {
    "net_buy": 3200,
    "trend": "순매수"
  },
  "market_momentum": {
    "kospi_change": 0.012,
    "trend": "상승"
  },
  "risk_signal": {
    "fomo": true,
    "panic": false
  },
  "confidence": 0.74,
  "reason": [
    "외국인 순매수 지속",
    "변동성 감소",
    "시장 상승 흐름"
  ]
}
```

### 전달 방식 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| `risk_signal.fomo` / `risk_signal.panic` | **bool** 유지 | 불/베어가 `if fomo: 탐욕 경고 논거 추가` 형태로 즉시 사용 가능 |
| `sentiment_score` | **0~1 float** | 오케스트레이터 `agreement_score` 계산 시 입력값으로 활용 |
| `confidence` | **0~1 float** | 지표 간 방향 불일치 시 낮아짐. 오케스트레이터가 심리 데이터 비중 조정에 사용 |
| V-KOSPI 일별 배열 | **미전달** | 현재값 + 주간 변화량만 전달. 추세는 `change_weekly` 부호로 판단 가능 |

---

## 4. 에이전트 출력 → 불/베어 입력 매핑

> 각 에이전트의 출력 필드가 불/베어 공통 입력 패키지의 어느 위치에, 어떤 처리를 거쳐 들어가는지 명시한다.
> **"그대로"** = 가공 없이 복사 / **"제외"** = 불/베어에 미전달 (에이전트 내부 분석용)

### 4-1. 매크로 에이전트 출력 → `macro` 필드

| 출력 필드 | 입력 위치 | 처리 | 불(Bull) 활용 | 베어(Bear) 활용 |
|---|---|---|---|---|
| `macro_regime` | `macro.macro_regime` | 그대로 | 골디락스/리플레이션이면 강세 배경 인용 | 스태그/과열이면 약세 배경 인용 |
| `regime_reason` | `macro.regime_reason` | 그대로 | 낙관 해석의 맥락 설명 | 비관 해석의 맥락 설명 |
| `bull_ammunition[]` | `macro.bull_ammunition` | 그대로 | **직접 논거로 사용** | 반박 대상으로 사용 |
| `bear_ammunition[]` | `macro.bear_ammunition` | 그대로 | 반박 대상으로 사용 | **직접 논거로 사용** |
| `key_risk` | `macro.key_risk` | 그대로 | 리스크 축소 논리 전개 | 리스크 부각 논리 전개 |
| `macro_score` | `macro.macro_score` | 그대로 | 불/베어 직접 미사용 | 불/베어 직접 미사용 → **오케스트레이터 agreement_score 계산에만 사용** |
| 추세 문자열 (내부) | — | **제외** | — | — |

---

### 4-2. 섹터종목 에이전트 출력 → `sector` 필드

| 출력 필드 | 입력 위치 | 처리 | 불(Bull) 활용 | 베어(Bear) 활용 |
|---|---|---|---|---|
| `supply_demand.foreign_net_20d/60d/120d` | `sector.supply_demand.*` | 그대로 (누적값) | 순매수 전환 구간 부각 | 지속 순매도 규모 직접 인용 |
| `supply_demand.foreign_consecutive_sell_5d` | `sector.supply_demand.*` | 그대로 | 매도 완화 시 반등 기대 근거 | 연속 매도일수 직접 인용 |
| `supply_demand.sell_intensity` | `sector.supply_demand.*` | 그대로 | 심화→완화 흐름이면 긍정 신호 | "심화" 레이블 직접 인용 |
| `earnings.quarters[]` | `sector.earnings.quarters` | 그대로 (4분기) | QoQ 반등 분기 부각 | 혼조 추세·불안정 부각 |
| `earnings.op_income_yoy/qoq` | `sector.earnings.*` | 그대로 | 높은 QoQ 성장률 근거 | YoY 낮거나 혼조 시 근거 |
| `earnings.earnings_trend_3q` | `sector.earnings.*` | 그대로 | "개선" 레이블 인용 | "혼조/악화" 레이블 인용 |
| `analyst_opinion.*` | `sector.analyst_opinion` | 그대로 (null 가능) | 목표주가 상향 시 긍정 근거 | 하향 또는 null → 불확실성 근거 |
| `sector_relative_strength.*` | `sector.sector_relative_strength` | 그대로 | RS 개선 구간 부각 | RS 약화 추세·종목 고유 이슈 부각 |
| `valuation.per/pbr` | `sector.valuation.*` | 그대로 | 저평가 구간이면 매수 기회 | 고평가 백분위 직접 인용 |
| `valuation.eps_yoy_change` | `sector.valuation.*` | 그대로 | EPS 성장률로 고PER 정당화 | EPS 하락 시 저평가 메리트 희석 근거 |
| 일별 수급 배열 (내부) | — | **제외** | — | — |

---

### 4-3. 시장심리 에이전트 출력 → `sentiment` 필드

| 출력 필드 | 입력 위치 | 처리 | 불(Bull) 활용 | 베어(Bear) 활용 |
|---|---|---|---|---|
| `sentiment_label` | `sentiment.sentiment_label` | 그대로 | "낙관" 시 시장 분위기 우호 근거 | "과열" 시 과매수 경고, "공포" 시 리스크 오프 근거 |
| `sentiment_score` | `sentiment.sentiment_score` | 그대로 | 0.6↑ → 우호적 심리 근거 | 0.8↑ → 과열 경고 근거 |
| `vkospi.value` / `change_weekly` | `sentiment.vkospi` | 그대로 | VIX 하락 → 불안 완화 근거 | VIX 상승 → 불안 심화 근거 |
| `foreign_flow.net_buy` / `trend` | `sentiment.foreign_flow` | 그대로 | 순매수 → 외국인 유입 근거 | 순매도 → 자본 이탈 근거 |
| `market_momentum.kospi_change` | `sentiment.market_momentum` | 그대로 | 상승 추세 확인 근거 | 하락 추세 리스크 근거 |
| `risk_signal.fomo` | `sentiment.risk_signal.fomo` | 그대로 (bool) | fomo=true → 매수 분위기 우호 (선택적) | **fomo=true → 과열 경고 핵심 근거** |
| `risk_signal.panic` | `sentiment.risk_signal.panic` | 그대로 (bool) | **panic=true → 역발상 반등 근거** | panic=true → 공포 심화 근거 |
| `confidence` | `sentiment.confidence` | 그대로 | 불/베어 직접 미사용 | 불/베어 직접 미사용 → **오케스트레이터가 심리 데이터 반영 비중 조정에 사용** |
| `reason[]` | `sentiment.reason` | 그대로 | 우호적 이유 선택 인용 | 부정적 이유 선택 인용 |

---

## 5. 불/베어 공통 입력 패키지

> 불 에이전트와 베어 에이전트는 **동일한 패키지**를 입력받는다.
> 해석 방향은 각 에이전트의 **시스템 프롬프트**로만 분리한다.

```json
{
  "topic": "삼성전자(005930) 지금 매수해도 되나?",
  "topic_type": "종목",

  "technical": {
    "ticker": "005930",
    "name": "삼성전자",
    "date": "2026-03-31",
    "price": 62500,
    "ma_5": 61800, "ma_20": 60200, "ma_60": 58900,
    "ma_120": 57100, "ma_200": 55000,
    "golden_cross_20_60": true,
    "rsi_14": 68.3,
    "macd_signal": "bullish_crossover",
    "bollinger_position": "upper_band_near",
    "disparity_20": 103.8,
    "volume_change_5d": 0.32,
    "support_level": 59000,
    "resistance_level": 64000
  },

  "macro": {
    "macro_regime": "스태그플레이션",
    "regime_reason": "...",
    "bull_ammunition": ["...", "..."],
    "bear_ammunition": ["...", "..."],
    "key_risk": "...",
    "macro_score": -0.6
  },

  "sector": {
    "supply_demand": { ... },
    "earnings": { ... },
    "analyst_opinion": { ... },
    "sector_relative_strength": { ... },
    "valuation": { ... },
  },

  "sentiment": {
    "sentiment_label": "낙관",
    "sentiment_score": 0.67,
    "vkospi": { "value": 18.2, "change_weekly": -2.3 },
    "foreign_flow": { "net_buy": 3200, "trend": "순매수" },
    "market_momentum": { "kospi_change": 0.012, "trend": "상승" },
    "risk_signal": { "fomo": true, "panic": false },
    "confidence": 0.74,
    "reason": ["..."]
  },

  "news_events": {
    "news_available": true,
    "recent_news": [
      { "title": "삼성전자 1분기 실적 예상치 상회", "source": "네이버금융", "date": "2026-03-30" }
    ],
    "recent_disclosures": [
      { "title": "분기보고서 제출", "date": "2026-02-14" }
    ],
    "analyst_report_summary": null
  }
}
```

> ⚠️ **수집 실패 시**: `news_available: false`, `recent_news: []`로 전달.
> 불/베어 에이전트 프롬프트에 다음 조건을 반드시 포함할 것:
> `"news_available이 false인 경우, 뉴스 및 공시 기반 논거는 사용하지 말 것."`
```

---

## 6. 불/베어 시스템 프롬프트 — 데이터 우선순위 지시

> 불/베어 에이전트는 전체 입력 패키지를 받되, 시스템 프롬프트에서 topic_type에 따라 어떤 데이터를 우선적으로 논거로 활용할지 지시한다.
> 이를 통해 토큰 낭비 없이 핵심 신호에 집중한 논거 생성을 유도한다.

```
[시스템 프롬프트 공통 지시]
입력 데이터 전체를 참고하되, topic_type에 따라 아래 우선순위로 논거를 구성하라.
arguments는 최대 3개이며, 우선순위가 높은 데이터 소스에서 먼저 논거를 선택하라.
```

| topic_type | 1순위 | 2순위 | 3순위 |
|---|---|---|---|
| `종목` | technical, sector | sentiment | macro |
| `시장전체` | macro, sentiment | technical | sector |
| `테마` | sector (RS), technical | macro, sentiment | — |

> ⏳ **미결 — 팀 논의 필요**: 위 우선순위가 도메인적으로 적절한지 확인 필요.
> 특히 종목 토론에서 macro를 3순위로 내리는 것이 맞는지 검토 요망.
> (매크로가 전체 시장 방향을 결정하는 큰 그림이므로 1순위 주장도 가능)

---

## 7. 불/베어 에이전트 출력 스펙

### 불 에이전트 출력

```json
{
  "stance": "bullish",
  "confidence": 0.72,
  "arguments": [
    { "claim": "20/60일선 골든크로스 발생으로 중기 추세 전환 신호", "data_ref": "technical.golden_cross_20_60" },
    { "claim": "QoQ 영업이익 +160% 서프라이즈, 실적 모멘텀 회복", "data_ref": "sector.earnings.op_income_qoq" },
    { "claim": "기준금리 하향 안정화로 유동성 압박 완화", "data_ref": "macro.bull_ammunition[0]" }
  ],
  "rebuttal": "Bear의 고평가 지적은 EPS +132% 성장률을 반영하지 않은 정적 해석",
  "summary": "실적 서프라이즈 + 기술적 전환 신호로 단기 매수 기회"
}
```

### 베어 에이전트 출력

```json
{
  "stance": "bearish",
  "confidence": 0.68,
  "arguments": [
    { "claim": "RSI 68.3 과매수 구간 진입, 단기 차익실현 압력 증가", "data_ref": "technical.rsi_14" },
    { "claim": "외국인 60일 누적 순매도 -33.3만억원, 수급 구조적 이탈", "data_ref": "sector.supply_demand.foreign_net_60d" },
    { "claim": "PBR 역사적 97분위, 밸류에이션 부담 과도", "data_ref": "sector.valuation.pbr_3y_percentile" }
  ],
  "rebuttal": "Bull의 골든크로스는 외국인·기관 동반 매도 심화 속 신뢰도 낮음",
  "summary": "수급 구조적 이탈 + 고평가로 추가 상승 여력 제한적"
}
```

---

## 8. 오케스트레이터 출력 스펙

**Input**: 불 에이전트 출력 + 베어 에이전트 출력 + 매크로 스코어 + 심리 confidence

```json
{
  "verdict": "bearish",
  "agreement_score": "1/3",
  "agreement_level": "약함",
  "conclusion_summary": "실적 모멘텀은 긍정적이나, 수급 구조 이탈과 역사적 고밸류에이션이 단기 리스크를 높인다. 장기 보유 목적이라면 분할 매수 고려, 단기 목적이라면 2~3주 대기 권고.",
  "key_data_points": [
    "외국인 60일 누적 순매도 -333,075억원",
    "PBR 3년 97분위 고평가",
    "RSI 68.3 과매수 구간"
  ],
  "bull_score": 0.72,
  "bear_score": 0.68
}
```

---

## 9. 결정 사항 확정 로그

| # | 항목 | 결정 | 비고 |
|---|---|---|---|
| 0 | `sector_summary` 제거 | ✅ **제거** | LLM 이중 해석 방지. 불/베어가 원본 필드 직접 읽음 |
| 1 | `arguments[].data_ref` 포함 여부 | ✅ **포함** | 근거 추적 가능. 토큰 비용 감수 |
| 2 | 토론 라운드 수 | ⏳ **팀 상의 후 결정** | MVP는 고정 2라운드로 시작 권장. Phase 1 구현 전 확정 필요 |
| 3 | 목표주가 크롤링 실패 시 | ✅ **DART 공시 목표주가로 대체 시도** | 대체도 실패 시 null + note 처리 |
| 4 | 시장 전체 토론 시 `sector` 필드 | ⏳ **Phase 2 때 설계** | 종목 토론 우선 구현. 시장/테마 토론은 `market_topic` 별도 스키마로 분리 예정 |
| 5 | `news_events` 수집 실패 시 | ✅ **수집 실패 플래그 + 뉴스 논거 생략 지시** | 불/베어 에이전트 프롬프트에 "news_available: false 시 뉴스 기반 논거 사용 금지" 조건 추가 필요 |

### 미확정 항목 처리 방침
- **#2 라운드 수**: Claude Code 작업 시작 전 팀 합의 후 이 문서에 업데이트할 것
- **#4 시장 전체 토론 스키마**: Phase 1(종목 토론) 완료 후 별도 설계 세션에서 확정할 것
- **#6 매크로 ammunition 유지 여부 (A안/B안)**: 팀 논의 후 확정. 결정 시 매크로 에이전트 출력 JSON과 Section 4-1 매핑 테이블 함께 수정할 것
- **#7 불/베어 데이터 우선순위**: 도메인 관점에서 종목 토론 시 macro 순위 재검토 필요. 팀 합의 후 Section 6 테이블 업데이트할 것
