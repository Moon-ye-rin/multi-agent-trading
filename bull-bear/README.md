# bull-bear/ — 불/베어 에이전트 모듈

멀티에이전트 투자 브리핑 시스템에서 **불(Bull) 에이전트**와 **베어(Bear) 에이전트**를 담당합니다.
두 에이전트는 동일한 입력 패키지를 받고, 시스템 프롬프트의 해석 프레임(낙관 vs 비관)만 다릅니다.

이 폴더의 `collectors/` 는 두 에이전트의 공통 입력 패키지 중 **`technical` 필드**를 채우는
데이터 수집 레이어입니다.

> 전체 에이전트 간 데이터 계약은 [`agent_interface_spec.md`](./agent_interface_spec.md) 참조.

---

## 폴더 구조

```
bull-bear/
├── collectors/
│   ├── __init__.py
│   └── technical_indicators.py   # 기술적 지표 수집
├── test_technical.py             # 동작 확인 스크립트
└── agent_interface_spec.md       # 에이전트 간 데이터 인터페이스 스펙 (Phase 0)
```

---

## 환경 설정

### 가상환경 생성 (uv)

```bash
# 프로젝트 루트에서
uv venv .venv_bullbear
uv pip install -r requirements.txt --python .venv_bullbear/bin/python
```

> **Python 3.13 주의사항**: `pykrx`가 내부적으로 `pkg_resources`를 사용하는데,
> setuptools 70+ 에서 top-level 노출이 제거되었습니다.
> `requirements.txt`에 `setuptools==69.5.1`이 고정되어 있으므로 별도 조치 불필요합니다.

---

## 불/베어 공통 입력 패키지 구조

스펙에 따라 두 에이전트는 아래 4개 필드를 입력받습니다.
현재 `collectors/` 는 그 중 `technical` 필드 수집만 구현되어 있습니다.

```
입력 패키지
├── technical    ← collectors/technical_indicators.py  [구현 완료]
├── macro        ← macro 에이전트 출력                  [미구현]
├── sector       ← sector/ 폴더 출력                    [구현 완료 — sector/ 참조]
└── sentiment    ← sentiment 에이전트 출력              [미구현]
```

---

## 파일별 역할 및 I/O

### `collectors/technical_indicators.py` — 기술적 지표 수집

**데이터 소스:** `pykrx` (OHLCV), `pandas_ta` (지표 계산)

**Input:**
```python
get_technical_indicators(
    ticker: str,        # 종목 코드  (예: "005930")
    ticker_name: str,   # 종목명     (예: "삼성전자")
) -> dict
```

**Output (`technical` 필드):**

```python
{
    # 기본 정보
    "ticker": str,
    "name":   str,
    "date":   "YYYY-MM-DD",     # 가장 최근 거래일
    "price":  float,            # 당일 종가 (원)

    # 이동평균선 (원, 해당 기간 데이터 부족 시 None)
    "ma_5":   float,
    "ma_20":  float,
    "ma_60":  float,
    "ma_120": float,
    "ma_200": float,

    # 크로스 신호 (20일선 × 60일선, 당일 발생 여부)
    "golden_cross_20_60": bool,   # 전일 MA20 < MA60, 당일 MA20 >= MA60
    "dead_cross_20_60":   bool,   # 전일 MA20 > MA60, 당일 MA20 <= MA60

    # 모멘텀 지표
    "rsi_14":             float,  # RSI 14일 (0~100)
    "macd_signal":        str,    # "bullish_crossover" | "bearish_crossover" | "bullish" | "bearish"
    "bollinger_position": str,    # "upper_band_near" | "middle" | "lower_band_near"
    "disparity_20":       float,  # 이격도 = price / MA20 × 100

    # 거래량
    "volume_change_5d": float,   # (최근 5일 평균 / 직전 5일 평균) - 1 (소수, 예: 0.32 = +32%)
    "volume_spike":     bool,    # 당일 거래량 > 20일 평균의 2배

    # 지지/저항 (최근 20일 고저가 기반)
    "support_level":    float,   # 최근 20일 저가
    "resistance_level": float,   # 최근 20일 고가
}
```

> 오류 발생 시 `{"error": str}` 반환.

**지표별 계산 방법 요약:**

| 지표 | 계산 방법 | 라이브러리 |
|---|---|---|
| 이동평균선 | `close.rolling(n).mean()` | pandas |
| 골든/데드크로스 | 전일→당일 MA20·MA60 부호 변화 감지 | pandas |
| RSI 14 | Wilder's Smoothing | pandas_ta |
| MACD | EMA(12) - EMA(26), 시그널 EMA(9) | pandas_ta |
| 볼린저 밴드 | 20일 이동평균 ± 2σ | pandas_ta |
| 이격도 | `price / MA20 × 100` | pandas |
| 거래량 변화율 | `(5일 평균) / (직전 5일 평균) - 1` | pandas |
| 지지/저항 | 최근 20일 저가/고가 | pandas |

**스펙 대비 추가 필드:**

| 필드 | 추가 이유 |
|---|---|
| `dead_cross_20_60` | 골든크로스 쌍으로 필요. Bear 에이전트 논거에 직접 활용 |
| `volume_spike` | 거래량 급등은 수급 이상 신호로 Bull/Bear 모두 논거로 활용 가능 |

---

### `test_technical.py` — 동작 확인 스크립트

기본 대상은 삼성전자(005930)이며, 스크립트 상단 `TICKER` / `TICKER_NAME` 변수를 수정해 다른 종목으로 변경할 수 있습니다.

**실행:**

```bash
# 프로젝트 루트에서
.venv_bullbear/bin/python bull-bear/test_technical.py

# 또는 bull-bear/ 폴더 안에서
cd bull-bear
../.venv_bullbear/bin/python test_technical.py
```

**출력 예시 (삼성전자 005930, 2026-03-31 기준):**

```
============================================================
  기술적 지표 수집 테스트 — 삼성전자 (005930)
============================================================

  기준일 : 2026-03-31
  현재가 : 167,200원

------------------------------------------------------------
  이동평균선
------------------------------------------------------------
  MA_5     : 178,460원
  MA_20    : 186,705원
  MA_60    : 170,038원
  MA_120   : 135,798원
  MA_200   : 108,694원

------------------------------------------------------------
  크로스 · 추세 신호
------------------------------------------------------------
  골든크로스(20×60)  : —
  데드크로스(20×60)  : —
  MACD 신호          : bearish
  볼린저 밴드 위치   : lower_band_near

------------------------------------------------------------
  모멘텀 지표
------------------------------------------------------------
  RSI 14             : 40.4
  이격도 (20일)      : 89.6%

------------------------------------------------------------
  거래량
------------------------------------------------------------
  5일 거래량 변화율  : +4.0%
  거래량 급등        : —

------------------------------------------------------------
  지지 / 저항
------------------------------------------------------------
  지지선  (20일 저가): 167,000원
  저항선  (20일 고가): 209,000원

============================================================
```

**출력 해석 가이드:**

| 항목 | 값 | 해석 |
|---|---|---|
| 이격도 89.6% | MA20 대비 -10.4% | 단기 하방 이격 심화, 평균 회귀 가능성 |
| RSI 40.4 | 40~50 중립 하단 | 과매도(30) 근접, 아직 반등 신호는 아님 |
| MACD bearish | 시그널선 하회 유지 | 단기 하락 추세 지속 중 |
| 볼린저 lower_band_near | 밴드 하단 20% 이내 | 단기 과매도 구간, 반등 여지 있음 |
| 골든/데드크로스 없음 | — | 전일 대비 당일 크로스 미발생 |
| 거래량 변화 +4% | 전주 대비 소폭 증가 | 뚜렷한 수급 신호 없음 |

---

## 현재 개발 상태

| 모듈 | 상태 | 비고 |
|---|---|---|
| `technical_indicators.py` | 완성 | pykrx + pandas_ta 기반 |
| 불 에이전트 (LLM) | 미구현 | `technical` 필드 수집만 완료 |
| 베어 에이전트 (LLM) | 미구현 | 동상 |
| `news_events` 수집 | 미구현 | 네이버 뉴스 + DART 공시 크롤링 필요 |
| 오케스트레이터 | 미구현 | Phase 3 대상 |
