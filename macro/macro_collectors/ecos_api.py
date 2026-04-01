import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from utils.logger import get_logger

logger = get_logger("ecos_api")

def fetch_ecos_data(api_key, stat_code, item_code, start_date, end_date, cycle_type="D"):
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    url = f"http://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/10000/{stat_code}/{cycle_type}/{start_str}/{end_str}/{item_code}"
    
    response = requests.get(url)
    data = response.json()
    if 'StatisticSearch' not in data:
        logger.error(f"데이터 조회 실패 (코드: {stat_code} / {item_code}): {data}")
        return pd.DataFrame()
        
    rows = data['StatisticSearch']['row']
    df_ecos = pd.DataFrame(rows)
    df_ecos['TIME'] = pd.to_datetime(df_ecos['TIME'])
    df_ecos.set_index('TIME', inplace=True)
    df_ecos['DATA_VALUE'] = df_ecos['DATA_VALUE'].astype(float)
    return df_ecos[['DATA_VALUE']]

def get_macro_raw_data() -> pd.DataFrame:
    """4개 핵심 거시 지표 수집 및 병합"""
    ECOS_API_KEY = os.getenv("ECOS_API_KEY")
    if not ECOS_API_KEY or ECOS_API_KEY == "your_ecos_api_key_here":
        raise ValueError("ECOS_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

    end_dt = datetime.today()
    start_dt = end_dt - timedelta(days=365)
    
    logger.info("  ▸ [ECOS] 주식/환율/금리 데이터 호출 중...")
    df_kospi = fetch_ecos_data(ECOS_API_KEY, "802Y001", "0001000", start_dt, end_dt)
    df_kospi.columns = ['KOSPI']
    
    df_usd = fetch_ecos_data(ECOS_API_KEY, "731Y001", "0000001", start_dt, end_dt)
    df_usd.columns = ['USD_KRW']
    
    df_bond_3y = fetch_ecos_data(ECOS_API_KEY, "817Y002", "010200000", start_dt, end_dt)
    df_bond_3y.columns = ['Bond_3Y']
    
    df_bond_10y = fetch_ecos_data(ECOS_API_KEY, "817Y002", "010210000", start_dt, end_dt)
    df_bond_10y.columns = ['Bond_10Y']
    
    df_corp_3y = fetch_ecos_data(ECOS_API_KEY, "817Y002", "010300000", start_dt, end_dt)
    df_corp_3y.columns = ['Corp_3Y']
    
    logger.info("  ▸ [ECOS] 데이터 병합 중...")
    df_merged = df_kospi.join([df_usd, df_bond_3y, df_bond_10y, df_corp_3y], how='outer')
    df_merged.ffill(inplace=True)
    df_merged.dropna(inplace=True)
    
    return df_merged