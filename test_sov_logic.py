# -*- coding: utf-8 -*-
"""
API 호출 없이(더미 history_df로) get_phase / get_baseline / PHASE_TARGETS 참조 로직을
검증하는 단위 테스트. `python fetch_sov.py` 없이 `python test_sov_logic.py`로 실행 가능.
"""
from datetime import date

import pandas as pd

import config
import fetch_sov as fs


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, label


def test_get_phase():
    check("사전 모니터링 (오늘=캠페인 시작 전)",
          fs.get_phase(date(2026, 9, 15)) == "캠페인 사전 모니터링")
    check("12월 -> 측정 체계 가동",
          fs.get_phase(date(2026, 12, 15)) == "측정 체계 가동")
    check("1월 -> 1차 리프트 확인",
          fs.get_phase(date(2027, 1, 10)) == "1차 리프트 확인")
    check("2월 -> 누적 성과 검증",
          fs.get_phase(date(2027, 2, 20)) == "누적 성과 검증")
    check("3월 이후 -> 캠페인 종료",
          fs.get_phase(date(2027, 3, 5)) == "캠페인 종료")


def test_get_baseline_no_data():
    empty = pd.DataFrame(columns=["period", "SOV"])
    baseline, confirmed = fs.get_baseline(empty)
    check("데이터 없으면 기본 베이스라인 16.7% 반환", baseline == config.BASELINE_DEFAULT)
    check("데이터 없으면 미확정(False)", confirmed is False)


def test_get_baseline_pre_campaign_only():
    # 캠페인 시작 전 실측치만 있는 경우 -> 베이스라인 갱신에 반영되면 안 됨 (참고용)
    df = pd.DataFrame({
        "period": ["2026-11-09", "2026-11-16", "2026-11-23"],
        "SOV": [15.2, 16.0, 16.4],
    })
    baseline, confirmed = fs.get_baseline(df)
    check("캠페인 시작 전 데이터만으로는 베이스라인 미확정", confirmed is False)
    check("미확정 시 기본값 16.7% 유지", baseline == config.BASELINE_DEFAULT)


def test_get_baseline_confirms_on_first_post_start_period():
    # 데이터랩 주간 period가 일요일 시작이라 "12월 1주차 월요일"과 정확히 안 맞는 상황을 재현.
    # 캠페인 시작일(2026-12-01, 화요일) 이후 첫 period는 일요일 시작 주간인 2026-11-29가 아니라
    # 그 다음 주 2026-12-06 (일)이 될 수 있음 -> 날짜 하나에 의존하지 않고 "시작일 이후 첫 실측치"를 잡아야 함.
    df = pd.DataFrame({
        "period": ["2026-11-22", "2026-11-29", "2026-12-06", "2026-12-13"],
        "SOV": [15.9, 16.3, 17.1, 17.4],
    })
    baseline, confirmed = fs.get_baseline(df)
    check("캠페인 시작일 이후 첫 실측치로 베이스라인 확정", confirmed is True)
    check("확정된 베이스라인 값이 해당 주차 SOV와 일치 (17.1)", baseline == 17.1)


def test_get_baseline_skips_missing_sov_rows():
    # 캠페인 시작 직후 주차 SOV가 결측이면 그 다음으로 실측이 존재하는 첫 주차를 잡아야 함.
    df = pd.DataFrame({
        "period": ["2026-11-29", "2026-12-06", "2026-12-13"],
        "SOV": [16.3, None, 18.0],
    })
    baseline, confirmed = fs.get_baseline(df)
    check("결측 주차는 건너뛰고 다음 실측치로 확정", confirmed is True)
    check("건너뛴 뒤 확정된 값 확인 (18.0)", baseline == 18.0)


def test_phase_targets_reference():
    check("12월 sov_target은 None (별도 목표 없음)",
          config.PHASE_TARGETS["측정 체계 가동"]["sov_target"] is None)
    check("1월 sov_target은 18.0 (18%대 진입)",
          config.PHASE_TARGETS["1차 리프트 확인"]["sov_target"] == 18.0)
    check("2월 sov_target은 20.0 (20%대+)",
          config.PHASE_TARGETS["누적 성과 검증"]["sov_target"] == 20.0)
    for phase_name, target in config.PHASE_TARGETS.items():
        check(f"{phase_name}에 sov_target_label 존재", bool(target.get("sov_target_label")))


if __name__ == "__main__":
    test_get_phase()
    test_get_baseline_no_data()
    test_get_baseline_pre_campaign_only()
    test_get_baseline_confirms_on_first_post_start_period()
    test_get_baseline_skips_missing_sov_rows()
    test_phase_targets_reference()
    print("\n전체 테스트 통과")
