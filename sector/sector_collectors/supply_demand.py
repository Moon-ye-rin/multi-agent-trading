"""
수급 흐름 수집 모듈 (pykrx)
외국인·기관·개인의 매수/매도 흐름과 강도 변화를 수집합니다.

[pykrx DataFrame 구조]
get_market_trading_value_by_investor() 반환값:
  - 인덱스(행): 투자자구분 (금융투자, 보험, 투신, 사모, 은행, 기타금융,
                             연기금, 기관합계, 외국인, 외국인기타, 개인, 전체)
  - 컬럼: 매도, 매수, 순매수 (단위: 원)

get_market_trading_value_by_date() 반환값 (일자별):
  - 인덱스(행): 날짜
  - 컬럼: 기관합계, 기타법인, 개인, 외국인합계, 전체 (단위: 원, 순매수 기준)
"""
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
from pykrx import stock
from utils.logger import get_logger

logger = get_logger("supply_demand")

ROW_FOREIGN     = "외국인"
ROW_INSTITUTION = "기관합계"
ROW_INDIVIDUAL  = "개인"
COL_NET         = "순매수"


def _to_100m(val: float) -> float:
    """
    pykrx 반환값(원)을 억원으로 변환.
    무조건 원 단위로 들어온다고 가정하고 10^8로 나눕니다.
    """
    if val is None or pd.isna(val):
        return 0.0
    
    # pykrx의 get_market_trading_value 계열은 기본적으로 '원' 단위입니다.
    # 100,000,000원 = 1억원
    return round(float(val) / 1e8, 1)


def _get_investor_summary(ticker: str, start_date: str, end_date: str) -> Optional[dict]:
    """
    투자자별 누적 순매수 합산 (억원)
    get_market_trading_value_by_investor → 인덱스=투자자구분, 컬럼=매도/매수/순매수
    """
    try:
        df = stock.get_market_trading_value_by_investor(start_date, end_date, ticker)
        if df is None or df.empty:
            logger.warning(f"수급 데이터 없음: {ticker} ({start_date}~{end_date})")
            return None

        logger.debug(f"  수급 컬럼: {list(df.columns)}, 인덱스: {list(df.index)}")

        def get_net(row_name: str) -> float:
            nonlocal df
            if row_name not in df.index:
                candidates = [i for i in df.index if row_name in i]
                if candidates:
                    row_name = candidates[0]
                else:
                    logger.warning(f"  '{row_name}' 행 없음. 가용 인덱스: {list(df.index)}")
                    return 0.0
            val = df.loc[row_name, COL_NET] if COL_NET in df.columns else 0
            return _to_100m(float(val))

        return {
            "foreign":       get_net(ROW_FOREIGN),
            "institutional": get_net(ROW_INSTITUTION),
            "individual":    get_net(ROW_INDIVIDUAL),
        }
    except Exception as e:
        logger.error(f"수급 데이터 조회 실패: {e}")
        return None


def _get_daily_net(ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    일자별 투자자 순매수 데이터 (연속 매수/매도 감지용)
    get_market_trading_value_by_date → 인덱스=날짜, 컬럼=기관합계/개인/외국인합계 등
    """
    try:
        df = stock.get_market_trading_value_by_date(start_date, end_date, ticker)
        if df is None or df.empty:
            return None
        logger.debug(f"  일자별 컬럼: {list(df.columns)}")
        return df
    except Exception as e:
        logger.error(f"일자별 수급 조회 실패: {e}")
        return None


def _find_col(df: pd.DataFrame, keyword: str) -> Optional[str]:
    matches = [c for c in df.columns if keyword in c]
    return matches[0] if matches else None


def get_supply_demand_analysis(ticker: str) -> dict:
    """
    수급 흐름 분석

    Returns:
        dict: {
            "20d":  { foreign, institutional, individual },  # 억원, 누적 순매수
            "60d":  { ... },
            "120d": { ... },
            "streak":            { 연속 매수/매도 감지 },
            "trend_consistency": bool,
            "intensity_change":  str,
        }
    """
    today = datetime.today().strftime("%Y%m%d")
    d20  = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")
    d60  = (datetime.today() - timedelta(days=90)).strftime("%Y%m%d")
    d120 = (datetime.today() - timedelta(days=180)).strftime("%Y%m%d")

    logger.info(f"[수급] 데이터 수집 시작: {ticker}")

    result: dict = {}

    # ── 1. 기간별 누적 순매수 ─────────────────────────────────────
    for period, start in [("20d", d20), ("60d", d60), ("120d", d120)]:
        result[period] = _get_investor_summary(ticker, start, today)

    if result["20d"] is None or result["60d"] is None:
        logger.error("[수급] 핵심 데이터(20d/60d) 수집 실패")
        return {"error": "데이터 수집 실패"}

    # ── 2. 연속 매수/매도 감지 (최근 5거래일) ──────────────────────
    daily_df = _get_daily_net(ticker, d20, today)

    streak: dict = {
        "foreign_consecutive_buy":  0,
        "foreign_consecutive_sell": 0,
        "institutional_5d_net":     None,
        "institutional_5d_trend":   "데이터 없음",
    }

    if daily_df is not None and not daily_df.empty:
        last5 = daily_df.tail(5)
        foreign_col = _find_col(last5, "외국인")
        inst_col    = _find_col(last5, "기관")

        if foreign_col:
            streak["foreign_consecutive_buy"]  = int((last5[foreign_col] > 0).sum())
            streak["foreign_consecutive_sell"] = int((last5[foreign_col] < 0).sum())

        if inst_col:
            inst_sum = last5[inst_col].sum()
            streak["institutional_5d_net"]   = _to_100m(float(inst_sum))
            streak["institutional_5d_trend"] = "매수우위" if inst_sum > 0 else "매도우위"

    result["streak"] = streak

    # ── 3. 단기·중기 방향 일치 여부 ────────────────────────────────
    f20 = result["20d"]["foreign"]
    f60 = result["60d"]["foreign"]
    result["trend_consistency"] = (f20 > 0) == (f60 > 0)

    # ── 4. 매도 강도 심화 여부 ──────────────────────────────────────
    avg_20 = f20 / 20 if f20 else 0
    avg_60 = f60 / 60 if f60 else 0
    if f20 < 0 and avg_20 < avg_60:
        result["intensity_change"] = "매도 강도 심화"
    elif f20 > 0 and avg_20 > avg_60:
        result["intensity_change"] = "매수 강도 심화"
    else:
        result["intensity_change"] = "강도 유지 또는 완화"

    logger.info(
        f"[수급] 수집 완료 | 외국인20d: {f20}억, "
        f"기관20d: {result['20d']['institutional']}억"
    )
    return result
