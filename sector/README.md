# sector/ — 섹터/종목 에이전트 모듈

멀티에이전트 투자 브리핑 시스템에서 **섹터 에이전트** 역할을 담당합니다.
종목 하나에 대해 5가지 데이터(수급·실적·목표주가·상대강도·밸류에이션)를 수집하고,
불/베어 에이전트에게 전달할 정형 페이로드를 생성합니다.

---

## 폴더 구조

```
sector/
├── sector_main.py              # 실행 진입점 (콘솔 출력 + JSON 저장)
├── test.py                     # 네이버 증권 종목분석 리포트 크롤러 (독립 실행, 테스트용)
├── sector_agents/
│   └── sector_agent.py         # 통합 오케스트레이터 (5개 수집 모듈 순차 실행)
├── sector_collectors/
│   ├── supply_demand.py        # 수급 분석 (pykrx)
│   ├── earnings.py             # 실적 분석 — 영업이익·매출액 (DART API)
│   ├── naver_finance.py        # 목표주가·투자의견 (네이버 증권 크롤링)
│   ├── relative_strength.py    # 섹터 상대강도 (pykrx)
│   ├── valuation.py            # 밸류에이션 — PER·PBR (pykrx)
│   └── consensus_test.py       # 한경컨센서스 크롤러 (독립 실행용, PDF 링크 포함)
├── utils/
│   └── logger.py               # 공통 로거
├── patch_pykrx.py              # pykrx 호환성 패치
├── requirements.txt
└── .env.example
```

---

## 데이터 흐름

```
sector_main.py
    └─▶ run_sector_agent(ticker, ticker_name, sector_etf)
            ├── [1/4] supply_demand.py      → payload["supply_demand"]
            ├── [2/4] earnings.py           → payload["earnings"]
            ├── [3/4] naver_finance.py      → payload["naver_finance"]
            └── [4/4] relative_strength.py  → payload["relative_strength"]
                       valuation.py         → payload["valuation"]
                                                    ↓
                                        콘솔 출력 + JSON 저장 (output/)
```

---

## 파일별 역할 및 I/O

### `sector_main.py` — 실행 진입점

```bash
python sector_main.py
```

분석 대상은 `.env` 또는 아래 기본값을 사용합니다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `TARGET_TICKER` | `005930` | 종목 코드 |
| `TARGET_NAME` | `삼성전자` | 종목명 |
| `SECTOR_ETF_TICKER` | `091160` | 섹터 ETF 코드 (KODEX 반도체) |
| `OUTPUT_DIR` | `output` | JSON 저장 경로 |
| `SAVE_JSON` | `true` | JSON 저장 여부 |

**역할:** `run_sector_agent()` 호출 → 결과를 섹션별로 콘솔 출력 → `output/sector_agent_{ticker}_{timestamp}.json` 저장

---

### `sector_agents/sector_agent.py` — 통합 오케스트레이터

> `sys.path`에 `sector/` 루트를 자동 추가하므로 `sector_agents/` 내부에서도 직접 실행 가능합니다.

**Input:**
```python
run_sector_agent(
    ticker: str,        # 종목 코드  (예: "005930")
    ticker_name: str,   # 종목명     (예: "삼성전자")
    sector_etf: str,    # 섹터 ETF   (예: "091160")
) -> dict
```

**Output — 통합 페이로드:**
```jsonc
{
  "meta": {
    "ticker":      str,   // 종목 코드
    "ticker_name": str,   // 종목명
    "sector_etf":  str,   // 섹터 ETF 코드
    "as_of":       str    // 수집 시각 "YYYY-MM-DD HH:MM"
  },
  "supply_demand":     dict | null,  // supply_demand.py 반환값
  "earnings":          dict | null,  // earnings.py 반환값
  "naver_finance":     dict | null,  // naver_finance.py 반환값
  "relative_strength": dict | null,  // relative_strength.py 반환값
  "valuation":         dict | null,  // valuation.py 반환값
  "errors":            list[str]     // 수집 실패 항목 오류 메시지 목록
}
```

4개 수집 모듈을 순차 호출하며, 각 모듈이 예외를 던져도 나머지는 계속 실행됩니다.

---

### `sector_collectors/supply_demand.py` — 수급 분석

**데이터 소스:** `pykrx`

**Input:** `get_supply_demand_analysis(ticker: str)`

**Output:**
```jsonc
{
  // ── 기간별 누적 순매수 (억원, 양수=순매수 / 음수=순매도) ──
  "20d":  { "foreign": float, "institutional": float, "individual": float },
  "60d":  { "foreign": float, "institutional": float, "individual": float },
  "120d": { "foreign": float, "institutional": float, "individual": float },

  // ── 최근 5거래일 연속 흐름 ─────────────────────────────────
  "streak": {
    "foreign_consecutive_buy":  int,   // 최근 5거래일 중 외국인 순매수일 수
    "foreign_consecutive_sell": int,   // 최근 5거래일 중 외국인 순매도일 수
    "institutional_5d_net":     float, // 기관 5일 누적 순매수 (억원)
    "institutional_5d_trend":   str    // "매수우위" | "매도우위"
  },

  // ── 방향성 진단 ────────────────────────────────────────────
  "trend_consistency": bool, // 20d·60d 외국인 방향 일치 여부
  "intensity_change":  str   // "매수 강도 심화" | "매도 강도 심화" | "강도 유지 또는 완화"
}
```

> 20d·60d 핵심 데이터 수집 실패 시 `{"error": "데이터 수집 실패"}` 반환

---

### `sector_collectors/earnings.py` — 실적 분석

**데이터 소스:** DART OpenAPI (`DART_API_KEY` 필수)  
**수집 항목:** 영업이익·매출액 (당기순이익 미수집)

**Input:** `get_earnings_analysis(ticker: str)`

**Output:**
```jsonc
{
  "corp_code":     str,  // DART 기업 고유 코드
  "latest_period": str,  // 가장 최근에 데이터가 존재하는 분기 키 (예: "2025_3Q")

  // ── 분기별 실적 ────────────────────────────────────────────
  "quarters": {
    // 키: "YYYY_QQ" (예: "2025_3Q", "2025_2Q", "2024_ANN" 등)
    // 데이터 없는 분기는 null
    "<period>": {
      "op_income": float, // 영업이익 (억원)
      "revenue":   float  // 매출액   (억원)
    }
  },

  // ── YoY 변화율 (전년동기 대비, %) ─────────────────────────
  "yoy": {
    "op_income_chg": float | null, // 영업이익 YoY 변화율
    "revenue_chg":   float | null  // 매출액 YoY 변화율
  },

  // ── QoQ 변화율 (직전분기 대비, %) ─────────────────────────
  "qoq": {
    "op_income_chg": float | null  // 영업이익 QoQ 변화율
  },

  "trend_3q": str, // "3분기 연속 개선" | "3분기 연속 악화" | "혼조" | "데이터 부족"
  "note":     str  // 주의사항 메시지
}
```

> `DART_API_KEY` 미설정 시 더미 데이터 반환 (구조 확인용)  
> 어닝 서프라이즈/쇼크 판단은 불/베어 에이전트에게 위임합니다.

---

### `sector_collectors/naver_finance.py` — 목표주가·투자의견

**데이터 소스:** 네이버 증권 HTML 크롤링 (별도 API 키 불필요)

**Input:** `get_naver_finance_data(ticker: str)`

**Output:**
```jsonc
{
  // ── 현재 주가 정보 (pykrx) ────────────────────────────────
  "current_price_info": {
    "current_price":   float, // 현재가 (원)
    "change":          float, // 전일 대비 (원, 음수=하락)
    "change_pct":      float, // 등락률 (%)
    "volume":          float, // 거래량
    "market_cap_100m": float  // 시가총액 (억원)
  },

  // ── 애널리스트 의견 (네이버 종목분석 크롤링, 3개월 이내) ──
  "analyst_opinion": {
    "avg_target_price": {
      "1m": float | null, // 최근 1개월 평균 목표주가 (원)
      "3m": float | null  // 최근 3개월 평균 목표주가 (원)
    },
    "target_price_gap_rate": float | null, // 현재가 대비 1개월 평균 목표주가 괴리율 (%)
    "target_price_trend":    str,           // "상향" | "하향" | "유지" | "데이터 부족" | "N/A"
    "buy_ratio": {
      "1m": float | null, // 최근 1개월 매수 의견 비율 (%)
      "3m": float | null
    },
    "report_count": {
      "1m": int, // 최근 1개월 리포트 수
      "3m": int  // 최근 3개월 리포트 수
    },
    "source": "naver_crawl",
    "note":   str
  },

  "as_of": str // 수집 시각 "YYYY-MM-DD HH:MM"
}
```

> 크롤링 특성상 네이버 증권 HTML 구조 변경 시 파싱 실패 가능.  
> 수집 실패 시 모든 필드를 `null`로 채운 빈 구조체를 반환합니다.  
> 요청 간 딜레이(`NAVER_REQUEST_DELAY`)는 `.env`로 조정합니다.

---

### `sector_collectors/relative_strength.py` — 섹터 상대강도

**데이터 소스:** `pykrx`

**Input:** `get_relative_strength_analysis(ticker: str, sector_etf: str)`

**Output:**
```jsonc
{
  "sector_etf": str, // 비교 대상 섹터 ETF 코드

  // ── 기간별 수익률 비교 ─────────────────────────────────────
  "rs_history": {
    // 키: "1m" | "3m" | "6m" | "1y"
    "<period>": {
      "stock_ret":    float, // 종목 수익률 (%)
      "sector_ret":   float, // 섹터 ETF 수익률 (%)
      "kospi_ret":    float, // KOSPI 수익률 (%)
      "rs_vs_sector": float, // 종목 - 섹터 (양수: 섹터 대비 강세)
      "rs_vs_kospi":  float  // 종목 - KOSPI (양수: 시장 대비 강세)
    }
  },

  // ── 상대강도 진단 ──────────────────────────────────────────
  "rs_trend":         str, // "지속 개선" | "지속 약화" | "최근 반전 (약화→개선)" | "최근 반전 (개선→약화)" | "혼조"
  "sector_issue":     str, // "섹터 전체 약세" | "종목 고유 약세" | "종목 상대 강세" | "섹터·종목 모두 KOSPI 상회"
  "strongest_period": str  // 상대강도 최고 구간 ("1m" | "3m" | "6m" | "1y")
}
```

---

### `sector_collectors/valuation.py` — 밸류에이션

**데이터 소스:** `pykrx` (3년 펀더멘털 이력)

**Input:** `get_valuation_analysis(ticker: str)`

**Output:**
```jsonc
{
  // ── 현재 밸류에이션 지표 ───────────────────────────────────
  "current": {
    "base_date": str,   // 데이터 기준일 (장 휴일 시 최근 영업일로 자동 소급)
    "per":       float, // Price-Earnings Ratio
    "pbr":       float, // Price-Book Ratio
    "eps":       float, // 주당순이익 (원)
    "bps":       float, // 주당순자산 (원)
    "div_yield": float  // 배당수익률 (%)
  },

  // ── 3년 밴드 분석 ──────────────────────────────────────────
  // per_band / pbr_band 동일 구조
  "per_band": {
    "current":   float, // 현재값
    "min_3y":    float, // 3년 최저
    "max_3y":    float, // 3년 최고
    "median_3y": float, // 3년 중간값
    "pct_3y":    float  // 3년 내 현재 백분위 (%, 낮을수록 저평가)
  },
  "pbr_band": { /* 동일 구조 */ },

  // ── 평가 레이블 ────────────────────────────────────────────
  "per_label":   str,   // "역사적 저평가 구간 (하위 20%)" | "역사적 중간 구간" | "역사적 고평가 구간 (상위 20%)"
  "pbr_label":   str,

  "eps_trend":   str,   // "EPS 개선 (YoY)" | "EPS 악화 (YoY)" | "데이터 부족"
  "eps_yoy_chg": float, // EPS YoY 변화율 (%)
  "note":        str    // 저평가+EPS악화 등 특이사항 메시지
}
```

> 최대 7일 소급하여 유효한 펀더멘털 데이터를 탐색합니다.  
> 7일 내 데이터 없으면 `{"error": "최근 유효 데이터 없음"}` 반환.

---

### `utils/logger.py` — 공통 로거

**Input:** `get_logger(name: str) -> logging.Logger`

`LOG_LEVEL` 환경변수로 로그 레벨을 조정합니다 (기본: `INFO`).  
포맷: `[YYYY-MM-DD HH:MM:SS] LEVEL | name | message`

---

## 환경 설정

`.env.example`을 복사하여 `.env`를 생성합니다.

```bash
cp .env.example .env
```

| 환경변수 | 필수 여부 | 설명 |
|---|---|---|
| `DART_API_KEY` | 필수 | [DART OpenAPI](https://opendart.fss.or.kr) 발급 (없으면 더미 데이터) |
| `TARGET_TICKER` | 선택 | 분석 종목 코드 (기본: `005930`) |
| `TARGET_NAME` | 선택 | 분석 종목명 (기본: `삼성전자`) |
| `SECTOR_ETF_TICKER` | 선택 | 섹터 ETF 코드 (기본: `091160`) |
| `NAVER_REQUEST_DELAY` | 선택 | 네이버 크롤링 딜레이 초 (기본: `1.0`) |
| `LOG_LEVEL` | 선택 | 로그 레벨 (기본: `INFO`) |
| `SAVE_JSON` | 선택 | JSON 저장 여부 (기본: `true`) |

---

## 설치 및 실행

```bash
pip install -r requirements.txt
python sector_main.py
```

---

## 현재 개발 상태

| 모듈 | 상태 | 비고 |
|---|---|---|
| `supply_demand.py` | 완성 | pykrx 기반 |
| `earnings.py` | 완성 | 영업이익·매출액만 수집 / DART API 키 필요 / 없으면 더미 데이터 |
| `naver_finance.py` | 완성 | HTML 구조 변경 시 파싱 재검토 필요 |
| `relative_strength.py` | 완성 | pykrx 기반 |
| `valuation.py` | 완성 | pykrx 기반, 장 휴일 자동 소급 |
| LLM 분석 (불/베어) | 미구현 | 페이로드 수집까지만 완료, 판단은 외부 에이전트에 위임 |
