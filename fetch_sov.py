# -*- coding: utf-8 -*-
"""
오쏘몰 SOV 대시보드 - 데이터 파이프라인

네이버 데이터랩 검색어트렌드 API를 호출해
1) SOV(검색 점유율) 산출에 필요한 6개 브랜드 검색지수
2) 비교의도 검색지수(오쏘몰 비교/후기/가격 검색지수 합)
를 주간 단위로 수집하고, 로컬 캐시(JSON)에 주차별 이력으로 누적 저장한다.

데이터랩 그룹 조회 한도는 5개이므로 SOV용 호출은 2회로 나누고,
"오쏘몰"을 두 호출에 공통 앵커로 넣어 두 번째 호출의 척도를 첫 번째 호출
기준으로 재보정(rescale)한 뒤 합산한다. (데이터랩 지수는 절대 검색량이 아니라
호출 단위 그룹 내 최대값=100 기준 상대 지수이므로, 두 호출의 척도가 서로 다르다.)
"""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

import config

BASE_DIR = Path(__file__).resolve().parent
CACHE_PATH = BASE_DIR / config.CACHE_DIR / config.CACHE_FILE

KST = ZoneInfo("Asia/Seoul")

DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


def _load_credentials():
    """NAVER_CLIENT_ID / SECRET을 .env(로컬) 또는 st.secrets(배포)에서 읽는다."""
    load_dotenv(BASE_DIR / ".env")
    load_dotenv(BASE_DIR.parent / ".env")  # 레포 루트 .env 재사용

    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")

    if not client_id or not client_secret:
        try:
            import streamlit as st  # 로컬 스크립트 실행 시엔 없을 수 있음

            client_id = client_id or st.secrets.get("NAVER_CLIENT_ID")
            client_secret = client_secret or st.secrets.get("NAVER_CLIENT_SECRET")
        except Exception:
            pass

    if not client_id or not client_secret:
        raise RuntimeError(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET을 찾을 수 없습니다. "
            ".env 파일 또는 st.secrets에 설정해주세요."
        )
    return client_id, client_secret


def fetch_datalab(keyword_groups, start_date, end_date, time_unit="week"):
    client_id, client_secret = _load_credentials()
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": time_unit,
        "keywordGroups": keyword_groups,
    }
    res = requests.post(DATALAB_URL, headers=headers, data=json.dumps(body), timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"데이터랩 API 에러 {res.status_code}: {res.text}")
    return res.json()


def _result_to_series(result):
    """{그룹명: {기간: 지수}} 형태로 변환"""
    series = {}
    for group in result.get("results", []):
        series[group["title"]] = {p["period"]: p["ratio"] for p in group["data"]}
    return series


def _brand_groups(brands):
    return [{"groupName": b, "keywords": [b]} for b in brands]


def fetch_sov_raw(start_date, end_date):
    """SOV 산출용 6개 브랜드 검색지수를 2회 호출로 수집 후 앵커 재보정하여 병합"""
    result1 = fetch_datalab(_brand_groups(config.CALL1_BRANDS), start_date, end_date, config.TIME_UNIT)
    result2 = fetch_datalab(_brand_groups(config.CALL2_BRANDS), start_date, end_date, config.TIME_UNIT)

    series1 = _result_to_series(result1)
    series2 = _result_to_series(result2)

    anchor = config.TARGET
    periods = sorted(set(series1.get(anchor, {})) | set(series2.get(anchor, {})))

    rows = []
    for period in periods:
        anchor1 = series1.get(anchor, {}).get(period)
        anchor2 = series2.get(anchor, {}).get(period)

        row = {"period": period}
        for comp in config.CALL1_BRANDS[1:]:
            row[comp] = series1.get(comp, {}).get(period)
        row[config.TARGET] = anchor1

        # call2 값을 call1 척도로 재보정: factor = call1의 오쏘몰값 / call2의 오쏘몰값
        factor = None
        if anchor1 is not None and anchor2:
            factor = anchor1 / anchor2

        for comp in config.CALL2_BRANDS[1:]:
            val = series2.get(comp, {}).get(period)
            row[comp] = round(val * factor, 4) if (val is not None and factor is not None) else None

        rows.append(row)

    return pd.DataFrame(rows)


def compute_sov(df):
    """SOV(t) = 오쏘몰(t) / Σ(오쏘몰 + 경쟁사 5종)(t) × 100"""
    df = df.copy()
    cols = [config.TARGET] + config.COMPETITORS
    valid = df[cols].notna().all(axis=1)
    denom = df[cols].sum(axis=1)
    df["SOV"] = None
    df.loc[valid, "SOV"] = (df.loc[valid, config.TARGET] / denom[valid] * 100).round(2)
    return df


def fetch_comparison_intent(start_date, end_date):
    """비교의도 검색지수 = "오쏘몰 비교"+"오쏘몰 후기"+"오쏘몰 가격" 검색지수 합"""
    result = fetch_datalab(_brand_groups(config.COMPARISON_KEYWORDS), start_date, end_date, config.TIME_UNIT)
    series = _result_to_series(result)

    # 검색량이 거의 없는 문구(예: "오쏘몰 비교")는 데이터랩이 해당 기간 자체를 빈 배열로
    # 돌려줄 수 있다. 이 경우 그 문구의 기여분을 0으로 간주해 합산한다(전체 None 처리 X).
    periods = sorted(set().union(*[set(v.keys()) for v in series.values()]) if series else [])
    rows = []
    for period in periods:
        vals = [series.get(kw, {}).get(period, 0) for kw in config.COMPARISON_KEYWORDS]
        rows.append({"period": period, "비교의도지수": round(sum(vals), 2)})
    return pd.DataFrame(rows)


def is_complete_week(period_str, today=None):
    """해당 period(주 시작일)가 오늘 기준으로 완전히 끝난 주인지 판별.
    데이터랩은 진행 중인 주도 그때까지 쌓인 부분 데이터를 돌려주므로,
    끝나지 않은 주는 차트/타일에서 제외해야 다른 주차와 비교가 왜곡되지 않는다."""
    today = today or date.today()
    period_start = date.fromisoformat(period_str)
    period_end = period_start + timedelta(days=6)
    return period_end <= today


def get_phase(today=None):
    """오늘 날짜 기준 캠페인 국면을 자동 판별한다.
    아직 오지 않은 집행 기간을 실행한 것처럼 보여주지 않는 것이 핵심 원칙이다."""
    today = today or date.today()
    if today < config.CAMPAIGN_START:
        return "캠페인 사전 모니터링"
    if today < config.DEC_END:
        return "측정 체계 가동"
    if today < config.JAN_END:
        return "1차 리프트 확인"
    if today < config.FEB_END:
        return "누적 성과 검증"
    return "캠페인 종료"


def get_baseline(history_df):
    """
    베이스라인은 기본 16.7%로 고정하되, 캠페인 시작일(config.CAMPAIGN_START) 이후 실측
    SOV가 history에 존재하면 그 중 가장 이른 시점 값으로 베이스라인을 정식 확정한다
    (하드코딩이 아니라 데이터 기반 재계산).

    "12월 1주차 월요일"처럼 특정 요일과 정확히 일치하는 period를 요구하지 않는다 —
    데이터랩이 반환하는 주간 period의 시작 요일(일요일/월요일)이 달라질 수 있어,
    날짜 하나에 의존하면 베이스라인이 영영 확정되지 않을 위험이 있기 때문이다.

    반환값: (baseline_value, is_confirmed)
    """
    if history_df is None or history_df.empty or "period" not in history_df.columns:
        return config.BASELINE_DEFAULT, False

    campaign_start_str = config.CAMPAIGN_START.strftime("%Y-%m-%d")
    post_start = history_df[
        (history_df["period"] >= campaign_start_str) & history_df["SOV"].notna()
    ].sort_values("period")

    if not post_start.empty:
        return float(post_start.iloc[0]["SOV"]), True
    return config.BASELINE_DEFAULT, False


def load_history():
    if not CACHE_PATH.exists():
        return pd.DataFrame(columns=["period", config.TARGET, *config.COMPETITORS, "SOV", "비교의도지수"])
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data.get("history", []))


def save_history(df, last_updated=None):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_updated": last_updated or datetime.now(KST).isoformat(timespec="seconds"),
        "history": df.to_dict(orient="records"),
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_meta():
    if not CACHE_PATH.exists():
        return {"last_updated": None}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {"last_updated": data.get("last_updated")}


def refresh(lookback_weeks=config.LOOKBACK_WEEKS):
    """API를 호출해 최근 lookback_weeks 주간 데이터를 가져오고 기존 캐시와 병합(주차 업데이트)한다."""
    end = date.today()
    start = end - timedelta(weeks=lookback_weeks)
    start_str, end_str = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    sov_df = fetch_sov_raw(start_str, end_str)
    sov_df = compute_sov(sov_df)
    intent_df = fetch_comparison_intent(start_str, end_str)

    merged = pd.merge(sov_df, intent_df, on="period", how="outer")

    existing = load_history()
    if not existing.empty:
        combined = pd.concat([existing, merged], ignore_index=True)
        combined = combined.drop_duplicates(subset="period", keep="last")
    else:
        combined = merged

    combined = combined.sort_values("period").reset_index(drop=True)
    save_history(combined)
    return combined


if __name__ == "__main__":
    df = refresh()
    print(f"캐시 저장 완료: {CACHE_PATH} ({len(df)}개 주차)")
    print(df.tail(12).to_string(index=False))
