"""
실적·공시 수집 모듈 (DART API)
최근 분기 실적 및 YoY·QoQ 변화를 수집합니다.
어닝 서프라이즈/쇼크 판단은 불/베어 에이전트에게 위임합니다.
"""
import io
import os
import zipfile
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger("earnings")

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_BASE_URL = "https://opendart.fss.or.kr/api"


# ── DART 분기 코드 정의 ──────────────────────────────────────────
# 11013: 1분기, 11012: 반기(2Q), 11014: 3분기, 11011: 사업보고서(연간)
QUARTER_MAP = {
    "2025_3Q": ("2025", "11014"),
    "2025_2Q": ("2025", "11012"),
    "2025_1Q": ("2025", "11013"),
    "2024_ANN": ("2024", "11011"),
    "2024_3Q": ("2024", "11014"),
    "2024_2Q": ("2024", "11012"),
    "2024_1Q": ("2024", "11013"),
}


def _get_corp_code(stock_code: str) -> Optional[str]:
    """종목 코드로 DART corp_code 조회 (전체 기업 목록 ZIP 다운로드 방식)"""
    # company.json은 corp_code를 필수로 받으므로, stock_code 조회에는
    # corpCode.xml(ZIP) 전체 목록을 다운로드해서 매핑해야 함
    try:
        url = f"{DART_BASE_URL}/corpCode.xml"
        params = {"crtfc_key": DART_API_KEY}
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_data = zf.read("CORPCODE.xml")

        root = ET.fromstring(xml_data)
        for item in root.findall("list"):
            sc = (item.findtext("stock_code") or "").strip()
            if sc == stock_code:
                corp_code = (item.findtext("corp_code") or "").strip()
                return corp_code or None

        logger.warning(f"corp_code를 찾을 수 없음: {stock_code}")
        return None
    except Exception as e:
        logger.error(f"corp_code 조회 오류: {e}")
        return None


def _get_financial_snapshot(corp_code: str, year: str, reprt_code: str) -> dict:
    """
    DART 단일회사 주요 계정 조회
    반환: { "매출액": ..., "영업이익": ..., "당기순이익": ... }
    """
    try:
        url = f"{DART_BASE_URL}/fnlttSinglAcntAll.json"
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code":  corp_code,
            "bsns_year":  year,
            "reprt_code": reprt_code,
            "fs_div":     "CFS",   # 연결재무제표 우선, 없으면 OFS(개별)로 재시도
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "000":
            # 연결 없으면 개별 재무제표로 재시도
            params["fs_div"] = "OFS"
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

        if data.get("status") != "000" or not data.get("list"):
            return {}

        # 필요 계정만 추출
        target_accounts = {"매출액", "영업이익", "당기순이익"}
        result = {}
        for item in data["list"]:
            account = item.get("account_nm", "")
            if account in target_accounts:
                # thstrm_amount: 당기, unit 고려 (단위: 원)
                raw = item.get("thstrm_amount", "0").replace(",", "").replace("-", "0")
                try:
                    result[account] = int(raw)
                except ValueError:
                    result[account] = 0
        return result

    except Exception as e:
        logger.error(f"재무 데이터 조회 오류 ({year}/{reprt_code}): {e}")
        return {}


def _to_100m(value: int) -> float:
    """원 단위 → 억원 단위"""
    return round(value / 1e8, 1)


def _change_rate(now: float, prev: float) -> Optional[float]:
    """변화율 계산 (%)"""
    if prev == 0:
        return None
    return round((now - prev) / abs(prev) * 100, 1)


def get_earnings_analysis(ticker: str) -> dict:
    """
    실적 분석 (DART API)

    Returns:
        dict: {
            "corp_code": str,
            "quarters": { "2025_3Q": { op_income, revenue, net_income }, ... },
            "yoy": { op_income_chg, revenue_chg, net_income_chg },  # %
            "qoq": { op_income_chg },                               # %
            "trend_3q": str,   # 연속 개선 / 연속 악화 / 혼조
            "latest_period": str,
            "note": str,       # 데이터 주의사항
        }
    """
    if not DART_API_KEY or DART_API_KEY == "your_dart_api_key_here":
        logger.warning("[실적] DART API 키 미설정 → 더미 데이터로 대체")
        return _dummy_earnings()

    logger.info(f"[실적] DART corp_code 조회: {ticker}")
    corp_code = _get_corp_code(ticker)
    if not corp_code:
        logger.warning("[실적] corp_code 조회 실패 → 더미 데이터 사용")
        return _dummy_earnings()

    logger.info(f"[실적] 재무 데이터 수집 시작 (corp_code: {corp_code})")

    # 수집할 분기 목록 (최신순)
    quarters_to_fetch = [
        "2025_3Q", "2025_2Q", "2025_1Q",
        "2024_ANN", "2024_3Q", "2024_2Q",
    ]

    quarters: dict = {}
    for key in quarters_to_fetch:
        year, reprt_code = QUARTER_MAP[key]
        raw = _get_financial_snapshot(corp_code, year, reprt_code)
        if raw:
            quarters[key] = {
                "op_income":  _to_100m(raw.get("영업이익",   0)),
                "revenue":    _to_100m(raw.get("매출액",     0)),
                "net_income": _to_100m(raw.get("당기순이익", 0)),
            }
            logger.info(f"  {key}: 영업이익 {quarters[key]['op_income']}억")
        else:
            quarters[key] = None
            logger.warning(f"  {key}: 데이터 없음")

    # ── 최신 분기 기준 설정 ─────────────────────────────────────
    # 가장 최근에 데이터가 있는 분기를 latest로 사용
    latest_key = next((k for k in quarters_to_fetch if quarters.get(k)), None)
    latest = quarters.get(latest_key) if latest_key else None

    # ── YoY 비교 (전년동기) ─────────────────────────────────────
    yoy_key_map = {
        "2025_3Q": "2024_3Q",
        "2025_2Q": "2024_2Q",
        "2025_1Q": None,      # 2024_1Q 미수집
    }
    yoy_key = yoy_key_map.get(latest_key)
    yoy_data = quarters.get(yoy_key) if yoy_key else None

    yoy = {}
    if latest and yoy_data:
        yoy = {
            "op_income_chg":  _change_rate(latest["op_income"],  yoy_data["op_income"]),
            "revenue_chg":    _change_rate(latest["revenue"],    yoy_data["revenue"]),
            "net_income_chg": _change_rate(latest["net_income"], yoy_data["net_income"]),
        }

    # ── QoQ 비교 (직전분기) ─────────────────────────────────────
    qoq_key_map = {
        "2025_3Q": "2025_2Q",
        "2025_2Q": "2025_1Q",
    }
    qoq_key = qoq_key_map.get(latest_key)
    qoq_data = quarters.get(qoq_key) if qoq_key else None

    qoq = {}
    if latest and qoq_data:
        qoq = {
            "op_income_chg": _change_rate(latest["op_income"], qoq_data["op_income"]),
        }

    # ── 3분기 연속 트렌드 ───────────────────────────────────────
    trend_3q = _calc_trend(quarters)

    return {
        "corp_code":     corp_code,
        "latest_period": latest_key or "N/A",
        "quarters":      quarters,
        "yoy":           yoy,
        "qoq":           qoq,
        "trend_3q":      trend_3q,
        "note":          "컨센서스 없음. 불/베어 에이전트가 YoY·QoQ·트렌드를 종합 판단.",
    }


def _calc_trend(quarters: dict) -> str:
    """최근 3분기 영업이익 방향성 계산"""
    keys = ["2025_1Q", "2025_2Q", "2025_3Q"]
    vals = []
    for k in keys:
        q = quarters.get(k)
        if q and q.get("op_income") is not None:
            vals.append(q["op_income"])

    if len(vals) < 3:
        return "데이터 부족"
    if vals[2] > vals[1] > vals[0]:
        return "3분기 연속 개선"
    if vals[2] < vals[1] < vals[0]:
        return "3분기 연속 악화"
    return "혼조"


def _dummy_earnings() -> dict:
    """DART API 키 없을 때 반환하는 더미 데이터 (구조 확인용)"""
    logger.info("[실적] 더미 데이터 반환 (DART API 키 필요)")
    return {
        "corp_code":     "00126380",   # 삼성전자
        "latest_period": "2025_3Q",
        "quarters": {
            "2025_3Q":  {"op_income": 91733.0,  "revenue": 792047.0, "net_income": 74069.0},
            "2025_2Q":  {"op_income": 106500.0, "revenue": 840000.0, "net_income": 92000.0},
            "2025_1Q":  {"op_income": 62300.0,  "revenue": 790000.0, "net_income": 53200.0},
            "2024_ANN": {"op_income": 323477.0, "revenue": 3005763.0,"net_income": 342519.0},
            "2024_3Q":  {"op_income": 91834.0,  "revenue": 792000.0, "net_income": 79100.0},
            "2024_2Q":  None,
        },
        "yoy": {
            "op_income_chg":  -0.1,
            "revenue_chg":    0.0,
            "net_income_chg": -6.4,
        },
        "qoq": {
            "op_income_chg": -13.9,
        },
        "trend_3q": "혼조",
        "note": "⚠️ DART API 키 미설정 — 더미 데이터입니다. .env에 DART_API_KEY를 설정하세요.",
    }
