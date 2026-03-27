"""
섹터 상대강도 수집 모듈 (pykrx)
종목 수익률 vs 섹터 ETF vs KOSPI 상대 비교
"""
from datetime import datetime, timedelta
from typing import Optional
from pykrx import stock
from utils.logger import get_logger

logger = get_logger("relative_strength")


def _period_return(code: str, start_date: str, end_date: str) -> Optional[float]:
    """구간 수익률 계산 (%)"""
    try:
        df = stock.get_market_ohlcv(start_date, end_date, code)
        if df is None or df.empty or len(df) < 2:
            return None
        ret = (df["종가"].iloc[-1] / df["종가"].iloc[0] - 1) * 100
        return round(ret, 2)
    except Exception as e:
        logger.warning(f"수익률 계산 실패 ({code}, {start_date}~{end_date}): {e}")
        return None


def _index_return(index_ticker: str, start_date: str, end_date: str) -> Optional[float]:
    """KOSPI/KOSDAQ 지수 수익률 계산"""
    try:
        df = stock.get_index_ohlcv(start_date, end_date, index_ticker)
        if df is None or df.empty or len(df) < 2:
            return None
        ret = (df["종가"].iloc[-1] / df["종가"].iloc[0] - 1) * 100
        return round(ret, 2)
    except Exception as e:
        logger.warning(f"지수 수익률 계산 실패 ({index_ticker}): {e}")
        return None


def get_relative_strength_analysis(ticker: str, sector_etf: str) -> dict:
    """
    섹터 상대강도 분석

    Args:
        ticker:     종목 코드 (예: "005930")
        sector_etf: 섹터 ETF 코드 (예: "091160" = KODEX 반도체)

    Returns:
        dict: {
            "sector_etf": str,
            "rs_history": {
                "1m":  { stock_ret, sector_ret, kospi_ret, rs_vs_sector, rs_vs_kospi },
                "3m":  { ... },
                "6m":  { ... },
                "1y":  { ... },
            },
            "rs_trend":       str,   # 상대강도 추세 (개선/약화/혼조)
            "sector_issue":   str,   # 섹터 전체 약세인지, 종목 고유 이슈인지
            "strongest_period": str, # 상대강도가 가장 높은 구간
        }
    """
    today = datetime.today().strftime("%Y%m%d")
    KOSPI = "1001"   # KOSPI 지수 코드 (pykrx)

    periods = {
        "1m": (datetime.today() - timedelta(days=30)).strftime("%Y%m%d"),
        "3m": (datetime.today() - timedelta(days=90)).strftime("%Y%m%d"),
        "6m": (datetime.today() - timedelta(days=180)).strftime("%Y%m%d"),
        "1y": (datetime.today() - timedelta(days=365)).strftime("%Y%m%d"),
    }

    logger.info(f"[상대강도] 수집 시작: {ticker} vs {sector_etf}")

    rs_history = {}
    for label, start in periods.items():
        stock_ret  = _period_return(ticker,     start, today)
        sector_ret = _period_return(sector_etf, start, today)
        kospi_ret  = _index_return(KOSPI,       start, today)

        rs_vs_sector = round(stock_ret - sector_ret, 2) if stock_ret is not None and sector_ret is not None else None
        rs_vs_kospi  = round(stock_ret - kospi_ret,  2) if stock_ret is not None and kospi_ret  is not None else None

        rs_history[label] = {
            "stock_ret":    stock_ret,
            "sector_ret":   sector_ret,
            "kospi_ret":    kospi_ret,
            "rs_vs_sector": rs_vs_sector,   # > 0: 섹터 대비 강세
            "rs_vs_kospi":  rs_vs_kospi,    # > 0: KOSPI 대비 강세
        }
        logger.info(
            f"  {label}: 종목 {stock_ret}%, 섹터 {sector_ret}%, "
            f"KOSPI {kospi_ret}%, RS(섹터) {rs_vs_sector}%p"
        )

    # ── 상대강도 추세 방향 ────────────────────────────────────────
    # 6m → 3m → 1m RS 변화로 추세 판단
    rs_6m = rs_history["6m"]["rs_vs_sector"]
    rs_3m = rs_history["3m"]["rs_vs_sector"]
    rs_1m = rs_history["1m"]["rs_vs_sector"]

    if all(v is not None for v in [rs_6m, rs_3m, rs_1m]):
        if rs_1m > rs_3m > rs_6m:
            rs_trend = "지속 개선"
        elif rs_1m < rs_3m < rs_6m:
            rs_trend = "지속 약화"
        elif rs_1m > rs_3m:
            rs_trend = "최근 반전 (약화→개선)"
        elif rs_1m < rs_3m:
            rs_trend = "최근 반전 (개선→약화)"
        else:
            rs_trend = "혼조"
    else:
        rs_trend = "데이터 부족"

    # ── 섹터 전체 약세 vs 종목 고유 이슈 ────────────────────────
    # 섹터도 KOSPI 대비 약세이고, 종목도 섹터 대비 약세면 → 섹터 전체 하락
    # 섹터는 KOSPI 대비 선방인데 종목만 섹터 대비 약세면 → 종목 고유 이슈
    sector_vs_kospi_1m = (
        round(rs_history["1m"]["sector_ret"] - rs_history["1m"]["kospi_ret"], 2)
        if rs_history["1m"]["sector_ret"] is not None and rs_history["1m"]["kospi_ret"] is not None
        else None
    )

    if rs_1m is not None and sector_vs_kospi_1m is not None:
        if rs_1m < 0 and sector_vs_kospi_1m < 0:
            sector_issue = "섹터 전체 약세 (종목+섹터 모두 KOSPI 하회)"
        elif rs_1m < 0 and sector_vs_kospi_1m >= 0:
            sector_issue = "종목 고유 약세 (섹터는 선방, 해당 종목만 부진)"
        elif rs_1m >= 0 and sector_vs_kospi_1m < 0:
            sector_issue = "종목 상대 강세 (섹터 약세 속 종목은 선방)"
        else:
            sector_issue = "섹터·종목 모두 KOSPI 상회"
    else:
        sector_issue = "판단 불가 (데이터 부족)"

    # 상대강도 최고 구간
    rs_vals = {k: rs_history[k]["rs_vs_sector"] for k in ["1m", "3m", "6m", "1y"] if rs_history[k]["rs_vs_sector"] is not None}
    strongest = max(rs_vals, key=rs_vals.get) if rs_vals else "N/A"

    return {
        "sector_etf":       sector_etf,
        "rs_history":       rs_history,
        "rs_trend":         rs_trend,
        "sector_issue":     sector_issue,
        "strongest_period": strongest,
    }
