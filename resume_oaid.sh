#!/bin/bash
# OpenAlex DOI→oaid 매핑 자동 재개 (매일 예산 리셋 후). 전량 완료 시 cron 자기제거.
cd /home/user/KISTI_Policy || exit 1
LOG="data_2025/.oaid_resume_$(date -u +%Y%m%d).log"
echo "=== 재개 $(date) ===" >> "$LOG"
KISTEP_BASE=/home/user/KISTEP /home/user/KISTI_Policy/.venv/bin/python build_oaid_index.py >> "$LOG" 2>&1
if grep -q "전량 처리" "$LOG"; then
  crontab -l 2>/dev/null | grep -v 'resume_oaid.sh' | crontab -
  echo "[$(date)] 매핑 전량 완료 → cron 자기제거" >> "$LOG"
fi
