#!/usr/bin/env bash
# KISTI Policy 배포 스크립트
# 사용법:
#   ./deploy.sh dev   → dev.kisti.ailibrary.kr
#   ./deploy.sh prod  → kisti.ailibrary.kr

set -euo pipefail

ENV="${1:-}"
if [[ "$ENV" != "dev" && "$ENV" != "prod" ]]; then
  echo "Usage: $0 {dev|prod}"
  echo ""
  echo "  dev  → dev.kisti.ailibrary.kr  (staging)"
  echo "  prod → kisti.ailibrary.kr       (production)"
  exit 1
fi

PROJECT="ailibrary-kisti"
REGION="asia-northeast1"

if [[ "$ENV" == "dev" ]]; then
  SERVICE="kisti-policy-dev"
  USERS_SECRET="kisti-users-dev"
  FLASK_SECRET="flask-secret-key-dev"
  URL="https://dev.kisti.ailibrary.kr"
  EMOJI="🧪"
else
  SERVICE="kisti-policy"
  USERS_SECRET="kisti-users"
  FLASK_SECRET="flask-secret-key"
  URL="https://kisti.ailibrary.kr"
  EMOJI="🚀"

  # prod 배포 전 확인
  echo "⚠️  PRODUCTION에 배포합니다: $URL"
  read -p "계속하시려면 'deploy'를 입력하세요: " CONFIRM
  if [[ "$CONFIRM" != "deploy" ]]; then
    echo "취소됨."
    exit 1
  fi
fi

echo ""
echo "$EMOJI $ENV 환경으로 배포 중..."
echo "   서비스: $SERVICE"
echo "   URL:    $URL"
echo ""

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT" \
  --allow-unauthenticated \
  --memory 1Gi \
  --port 8080 \
  --timeout 300 \
  --set-env-vars="GCP_PROJECT=$PROJECT,USERS_SECRET=$USERS_SECRET,FLASK_SECRET_NAME=$FLASK_SECRET" \
  --quiet

echo ""
echo "✅ 배포 완료: $URL"
