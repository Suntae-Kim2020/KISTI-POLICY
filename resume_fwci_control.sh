#!/bin/bash
# 비교군 OpenAlex 세계 상위판정·FWCI 수집 자동 재개 (매일 UTC 예산 리셋 직후).
# 전량 완료되면 세계 기준 회귀까지 자동 실행하고 cron 자기제거.
cd /home/user/KISTI_Policy || exit 1
LOG="data_2025/.fwci_resume_$(date -u +%Y%m%d).log"
echo "=== 재개 $(date) ===" >> "$LOG"
/home/user/KISTI_Policy/.venv/bin/python build_fwci_control.py >> "$LOG" 2>&1

if grep -q "\[전량 완료\]" "$LOG"; then
  echo "[$(date)] 수집 완료 → 세계 기준 회귀 확정치 산출" >> "$LOG"
  /home/user/KISTI_Policy/.venv/bin/python build_paper1_regression_world.py >> "$LOG" 2>&1
  crontab -l 2>/dev/null | grep -v 'resume_fwci_control.sh' | crontab -
  echo "[$(date)] 전량 완료 → cron 자기제거" >> "$LOG"
else
  echo "[$(date)] 예산 소진 — 내일 재개 예정" >> "$LOG"
fi
