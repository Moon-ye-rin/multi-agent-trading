"""
밸류에이션 분석 모듈 (pykrx)
PER·PBR 역사적 밴드 비교 및 고평가/저평가 판단용 데이터 수집
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
import pandas as pd
from pykrx import stock
from utils.logger import get_logger
logger = get_logger("valuation")

def _get_latest_available_fundamental(ticker: str, max_days: int = 7) -> Tuple[Optional[pd.DataFrame], str]:
    """
    현재부터 최대 max_days 전까지 거슬러 올라가며 유효한 펀더멘털 데이터를 찾음
    Returns: (DataFrame, found_date_str)
    """
    for i in range(max_days):
        target_date = (datetime.today() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df = stock.get_market_fundamental(target_date, target_date, ticker)
            if df is not None and not df.empty:
                # 데이터가 전부 0인 경우도 체크 (장 시작 직후 등)
                if df.iloc[0].get("EPS", 0) != 0 or df.iloc[0].get("BPS", 0) != 0:
                    return df, target_date
        except Exception:
            continue
    return None, ""

def get_valuation_analysis(ticker: str) -> dict:
    """
    밸류에이션 분석 (현재 데이터 부재 시 최근 영업일 데이터 자동 탐색)
    """
    # ── [수정] 현재 데이터 탐색 (데이터 없을 시 전날로 소급) ───────────────────
    fund_now, found_date = _get_latest_available_fundamental(ticker)
    
    if fund_now is None:
        # logger.error("[밸류에이션] 최근 7일 내 유효한 펀더멘털 데이터가 없음")
        return {"error": "최근 유효 데이터 없음 (상장 폐지 또는 데이터 오류)"}

    # 수집된 실제 기준일 설정
    today_dt = datetime.strptime(found_date, "%Y%m%d")
    today = found_date
    y1ago = (today_dt - timedelta(days=365)).strftime("%Y%m%d")
    y3ago = (today_dt - timedelta(days=365 * 3)).strftime("%Y%m%d")

    # logger.info(f"[밸류에이션] {found_date} 기준 3년 데이터 수집 시작: {ticker}")

    # ── 3년 이력 수집 ────────────────────────────────────
    try:
        # 3년치 밴드 데이터 수집
        fund_3y = stock.get_market_fundamental(y3ago, today, ticker)
    except Exception as e:
        return {"error": f"3년 데이터 수집 실패: {e}"}

    # ── 현재 지표 (found_date 기준) ──────────────────────────────
    row_now = fund_now.iloc[-1]
    per_now = float(row_now.get("PER", 0))
    pbr_now = float(row_now.get("PBR", 0))
    eps_now = float(row_now.get("EPS", 0))
    bps_now = float(row_now.get("BPS", 0))
    div_now = float(row_now.get("DIV", 0))

    current = {
        "base_date": found_date,  # 데이터 기준일 명시
        "per": round(per_now, 2),
        "pbr": round(pbr_now, 2),
        "eps": round(eps_now, 0),
        "bps": round(bps_now, 0),
        "div_yield": round(div_now, 2),
    }

    # ── 3년 역사적 밴드 함수 ─────────────────────────────────────────
    def build_band(series_raw: pd.Series, current_val: float) -> dict:
        series = series_raw.replace(0, float("nan")).dropna()
        if series.empty:
            return {}
        pct = round((series < current_val).sum() / len(series) * 100, 0)
        return {
            "current": round(current_val, 2),
            "min_3y": round(series.min(), 2),
            "max_3y": round(series.max(), 2),
            "median_3y": round(series.median(), 2),
            "pct_3y": pct,
        }

    per_band = {}
    pbr_band = {}
    eps_trend_str = "데이터 부족"
    eps_yoy_chg: Optional[float] = None

    if fund_3y is not None and not fund_3y.empty:
        per_band = build_band(fund_3y["PER"], per_now)
        pbr_band = build_band(fund_3y["PBR"], pbr_now)

        # EPS 1년 전 대비 변화 (YoY) - 1년 전 데이터도 소급 적용 가능하게 함수 재활용
        try:
            # 1년 전 날짜 근처 데이터 탐색
            fund_1y_all = stock.get_market_fundamental((today_dt - timedelta(days=370)).strftime("%Y%m%d"), y1ago, ticker)
            if not fund_1y_all.empty:
                eps_1y = float(fund_1y_all.iloc[-1].get("EPS", 0))
                if eps_1y != 0:
                    eps_yoy_chg = round((eps_now - eps_1y) / abs(eps_1y) * 100, 1)
                    eps_trend_str = "EPS 개선 (YoY)" if eps_yoy_chg > 0 else "EPS 악화 (YoY)"
        except Exception:
            pass

    # ── 고평가/저평가 레이블 및 주의사항 (기존 로직 동일) ───────────────────
    def valuation_label(pct: Optional[float]) -> str:
        if pct is None: return "판단 불가"
        if pct <= 20: return "역사적 저평가 구간 (하위 20%)"
        if pct >= 80: return "역사적 고평가 구간 (상위 20%)"
        return "역사적 중간 구간"

    per_label = valuation_label(per_band.get("pct_3y"))
    pbr_label = valuation_label(pbr_band.get("pct_3y"))

    note = ""
    if "저평가" in per_label and eps_yoy_chg is not None and eps_yoy_chg < -10:
        note = f"⚠️ PER 기준 저평가이지만 EPS가 전년 대비 {eps_yoy_chg}% 악화 중. 실적 추가 하향 시 저평가 메리트 희석 가능."
    elif "저평가" in per_label:
        note = "PER 기준 저평가 구간. 실적 트렌드와 함께 해석 필요."

    return {
        "current": current,
        "per_band": per_band,
        "pbr_band": pbr_band,
        "per_label": per_label,
        "pbr_label": pbr_label,
        "eps_trend": eps_trend_str,
        "eps_yoy_chg": eps_yoy_chg,
        "note": note,
    }