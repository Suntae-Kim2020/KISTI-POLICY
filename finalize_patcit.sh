#!/bin/bash
# 대조군 매핑 완료(내일) 후 원스텝: 집계 재조인 → 회귀 확정치.
cd /home/user/KISTI_Policy || exit 1
echo "=== 확정 분석 $(date) ==="
echo "[대조군 매핑 상태]"
python3 -c "import json; d=json.load(open('data_2025/oaid_control.json')); print(f'  oaid_control: {len(d):,} (목표 100,000)')"
echo "[1/3] 특허인용 재집계(build_patcit_join)"
.venv/bin/python build_patcit_join.py
echo "[2/3] 회귀 확정치(build_patcit_regression, df 자동 재빌드)"
.venv/bin/python build_patcit_regression.py
echo "[3/3] 강건성 II: 분야별 층화·성향점수매칭·함수형(build_patcit_hetero)"
.venv/bin/python build_patcit_hetero.py
echo "=== 완료 ==="
