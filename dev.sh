#!/usr/bin/env bash
# 로컬 개발 서버 실행
# 사용법: ./dev.sh [port]
#
# 동작:
#   1. .users_local.json이 있으면 사용 (Secret Manager 대신)
#   2. 없으면 dev Secret에서 초기화 (gcloud 인증 필요)
#   3. Flask 서버 시작 (기본 포트 5002)

set -euo pipefail

PORT="${1:-5002}"
PROJECT="ailibrary-kisti"
SECRET="kisti-users-dev"
LOCAL_FILE=".users_local.json"

cd "$(dirname "$0")"

# 로컬 사용자 파일 초기화 (최초 1회 또는 강제 새로고침)
if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "📥 로컬 사용자 파일이 없어 Secret '$SECRET'에서 다운로드..."
  gcloud secrets versions access latest --secret="$SECRET" --project="$PROJECT" > "$LOCAL_FILE"
  echo "   ✓ $LOCAL_FILE 생성됨 (.gitignore로 제외됨)"
fi

# 의존성 확인
if ! python3 -c "import flask, flask_login, bcrypt" 2>/dev/null; then
  echo "📦 의존성 설치 중..."
  pip3 install -q -r requirements.txt
fi

echo ""
echo "🏠 로컬 개발 서버 시작"
echo "   URL:     http://localhost:$PORT"
echo "   사용자:   $LOCAL_FILE (Secret Manager 대신 사용)"
echo "   초기 계정: kim.suntae@jbnu.ac.kr / admin1234!"
echo ""
echo "   Secret 갱신이 필요하면: rm $LOCAL_FILE && ./dev.sh"
echo ""

PORT="$PORT" \
FLASK_SECRET_KEY="local-dev-not-secure-do-not-use-in-prod" \
KISTEP_BASE="/Users/kimsuntae/KISTEP" \
python3 app.py
