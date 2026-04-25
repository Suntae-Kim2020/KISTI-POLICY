"""
감사 로그 모듈 — Firestore에 사용자 활동 기록

Collection: audit_events
Document 구조:
  timestamp: datetime (server time)
  email: str (이메일 소문자)
  event_type: str (login, login_failed, logout, download_zip, download_html)
  ip: str
  user_agent: str
  details: dict (이벤트별 추가 정보)
  session_id: str (login/logout 매칭용, 옵션)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from flask import request
from flask_login import current_user

_client = None
_client_init_failed = False


def _get_client():
    global _client, _client_init_failed
    if _client_init_failed:
        return None
    if _client is None:
        try:
            from google.cloud import firestore
            _client = firestore.Client(project=os.environ.get("GCP_PROJECT", "ailibrary-kisti"))
        except Exception as e:
            # 로컬 개발 환경(ADC 없음)에선 조용히 비활성화
            _client_init_failed = True
            try:
                from flask import current_app
                current_app.logger.warning(f"Firestore 비활성화: {e}")
            except Exception:
                pass
            return None
    return _client


def _request_meta():
    """요청에서 IP, User-Agent 추출."""
    try:
        # X-Forwarded-For (Cloud Run 환경)
        ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not ip:
            ip = request.remote_addr or ""
        ua = request.headers.get("User-Agent", "")[:500]  # 상한
        return ip, ua
    except Exception:
        return "", ""


def log_event(event_type: str, email: str = "", details: dict = None, session_id: str = None):
    """이벤트 기록. 실패해도 앱 동작에 영향 없도록 조용히 예외 처리."""
    client = _get_client()
    if client is None:
        return

    try:
        ip, ua = _request_meta()
        doc = {
            "timestamp": datetime.now(timezone.utc),
            "email": email.lower() if email else "",
            "event_type": event_type,
            "ip": ip,
            "user_agent": ua,
            "details": details or {},
        }
        if session_id:
            doc["session_id"] = session_id
        client.collection("audit_events").add(doc)
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"감사 로그 기록 실패: {e}")
        except Exception:
            pass


def new_session_id():
    return uuid.uuid4().hex


def query_events(email=None, event_type=None, since=None, until=None, limit=100):
    """감사 이벤트 조회. 최신순."""
    client = _get_client()
    if client is None:
        return []

    try:
        from google.cloud import firestore
        q = client.collection("audit_events")
        if email:
            q = q.where(filter=firestore.FieldFilter("email", "==", email.lower()))
        if event_type:
            q = q.where(filter=firestore.FieldFilter("event_type", "==", event_type))
        if since:
            q = q.where(filter=firestore.FieldFilter("timestamp", ">=", since))
        if until:
            q = q.where(filter=firestore.FieldFilter("timestamp", "<=", until))

        q = q.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)

        results = []
        for doc in q.stream():
            data = doc.to_dict()
            data["_id"] = doc.id
            results.append(data)
        return results
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"감사 로그 조회 실패: {e}")
        except Exception:
            pass
        return []


def last_login_map():
    """사용자별 최근 로그인 시각 매핑. {email: datetime}"""
    client = _get_client()
    if client is None:
        return {}

    try:
        from google.cloud import firestore
        # 최근 1000개 login 이벤트 조회 후 사용자별 집계
        q = (client.collection("audit_events")
             .where(filter=firestore.FieldFilter("event_type", "==", "login"))
             .order_by("timestamp", direction=firestore.Query.DESCENDING)
             .limit(1000))

        result = {}
        for doc in q.stream():
            data = doc.to_dict()
            email = data.get("email", "")
            if email and email not in result:
                result[email] = data.get("timestamp")
        return result
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"최근 로그인 조회 실패: {e}")
        except Exception:
            pass
        return {}


def delete_event(doc_id: str) -> bool:
    """감사 이벤트 단건 삭제. 성공 시 True."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.collection("audit_events").document(doc_id).delete()
        return True
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"감사 이벤트 삭제 실패 ({doc_id}): {e}")
        except Exception:
            pass
        return False


def user_summary(email):
    """특정 사용자의 요약 통계 (최근 로그인, 다운로드 횟수 등)"""
    client = _get_client()
    if client is None:
        return {}

    email = email.lower()
    try:
        from google.cloud import firestore
        # 최근 30일 이벤트
        since = datetime.now(timezone.utc) - timedelta(days=30)
        q = (client.collection("audit_events")
             .where(filter=firestore.FieldFilter("email", "==", email))
             .where(filter=firestore.FieldFilter("timestamp", ">=", since)))

        counts = {"login": 0, "login_failed": 0, "logout": 0,
                  "download_zip": 0, "download_html": 0}
        last_login = None
        for doc in q.stream():
            d = doc.to_dict()
            t = d.get("event_type", "")
            if t in counts:
                counts[t] += 1
            if t == "login":
                ts = d.get("timestamp")
                if ts and (last_login is None or ts > last_login):
                    last_login = ts
        return {"counts_30d": counts, "last_login": last_login}
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.error(f"사용자 요약 조회 실패: {e}")
        except Exception:
            pass
        return {}
