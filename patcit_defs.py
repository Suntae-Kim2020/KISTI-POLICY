#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""유발논문 정의(전체/외부) 공통 처리 — 회귀·강건성 스크립트에서 공유.

INDUCED_DEF 환경변수 또는 인자로 정의를 선택한다.
  external : 기관 소속 저자가 없는 유발논문만 (개정 정의, 기본값)
  all      : 사사표기가 있는 모든 유발논문 (현행 정의, 민감도 분석용)

org별 분석에서는 '해당 기관 소속 저자 유무'로 판정한다(다른 기관 소속은 무관).
"""
import os, json
from pathlib import Path

P = Path("/home/user/KISTI_Policy/data_2025")
EXT_JSON = P / "induced_external.json"


def mode():
    m = os.environ.get("INDUCED_DEF", "external").lower()
    if m not in ("external", "all"):
        raise SystemExit(f"INDUCED_DEF는 external|all 이어야 함 (입력: {m})")
    return m


def load_flags():
    """UT -> {"internal": [org...], "ext_any": bool}"""
    if not EXT_JSON.exists():
        raise SystemExit(f"[오류] {EXT_JSON} 없음 → build_induced_external.py 먼저 실행")
    return json.load(open(EXT_JSON))


def apply(df, org=None, flags=None, m=None):
    """유발 행만 정의에 따라 필터. 대조군(induced==0)은 그대로 둔다.

    org=None : 어느 기관에도 소속 저자가 없어야 유지 (합산 분석)
    org='ibs': IBS 소속 저자만 없으면 유지 (기관별 분석)
    """
    m = m or mode()
    if m == "all":
        return df
    flags = flags if flags is not None else load_flags()
    if org:
        keep = df.UT.map(lambda u: org not in flags.get(u, {}).get("internal", []))
    else:
        keep = df.UT.map(lambda u: flags.get(u, {}).get("ext_any", True))
    return df[(df.induced == 0) | keep]


def suffix(m=None):
    return (m or mode())
