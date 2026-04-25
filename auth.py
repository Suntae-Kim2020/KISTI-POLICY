"""
인증 모듈 — Flask-Login + Secret Manager + bcrypt
사용자 데이터: GCP Secret Manager (JSON)
로그인 실패 제한: 인스턴스 메모리 (5회 실패 → 10분 잠금)
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path

import bcrypt
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Email

from audit import log_event, new_session_id

# ── Secret Manager 연동 ──────────────────────────────────────
_USERS_CACHE = {"data": None, "ts": 0}
_CACHE_TTL = 30  # 초 (Secret 변경 반영 지연)

USERS_SECRET = os.environ.get("USERS_SECRET", "kisti-users")
PROJECT_ID = os.environ.get("GCP_PROJECT", "ailibrary-kisti")
LOCAL_USERS_FILE = Path(__file__).parent / ".users_local.json"

MAX_ATTEMPTS = 5
LOCKOUT_WINDOW = 600  # 10분
_FAILED_ATTEMPTS = {}  # {email: [ts, ts, ...]}


def _load_users_from_secret():
    """Secret Manager에서 사용자 JSON 로딩. 로컬 개발용 fallback 포함."""
    if LOCAL_USERS_FILE.exists():
        return json.loads(LOCAL_USERS_FILE.read_text(encoding="utf-8"))

    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{USERS_SECRET}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return json.loads(response.payload.data.decode("utf-8"))
    except Exception as e:
        current_app.logger.error(f"Secret Manager load failed: {e}")
        return {}


def load_users(force_refresh=False):
    """캐시된 사용자 목록 반환. 30초마다 재로딩."""
    now = time.time()
    if force_refresh or _USERS_CACHE["data"] is None or now - _USERS_CACHE["ts"] > _CACHE_TTL:
        _USERS_CACHE["data"] = _load_users_from_secret()
        _USERS_CACHE["ts"] = now
    return _USERS_CACHE["data"]


def save_users(users_dict):
    """사용자 목록을 Secret Manager에 저장 (새 version). 관리자 전용."""
    if LOCAL_USERS_FILE.exists():
        LOCAL_USERS_FILE.write_text(
            json.dumps(users_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _USERS_CACHE["data"] = None
        return

    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{PROJECT_ID}/secrets/{USERS_SECRET}"
    payload = json.dumps(users_dict, ensure_ascii=False).encode("utf-8")
    client.add_secret_version(
        request={"parent": parent, "payload": {"data": payload}}
    )
    _USERS_CACHE["data"] = None


# ── bcrypt 유틸 ──────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── 로그인 실패 제한 ─────────────────────────────────────────

def is_locked(email: str) -> int:
    """잠금 상태면 남은 초(int), 아니면 0."""
    attempts = _FAILED_ATTEMPTS.get(email, [])
    now = time.time()
    recent = [t for t in attempts if now - t < LOCKOUT_WINDOW]
    _FAILED_ATTEMPTS[email] = recent
    if len(recent) >= MAX_ATTEMPTS:
        remaining = int(LOCKOUT_WINDOW - (now - recent[0]))
        return max(0, remaining)
    return 0


def record_failure(email: str):
    _FAILED_ATTEMPTS.setdefault(email, []).append(time.time())


def clear_failures(email: str):
    _FAILED_ATTEMPTS.pop(email, None)


# ── User 모델 ────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, email: str, data: dict):
        self.id = email
        self.email = email
        self.name = data.get("name", email)
        self.is_admin = data.get("is_admin", False)
        self.created_at = data.get("created_at", "")


def load_user_by_id(user_id: str):
    users = load_users()
    if user_id in users:
        return User(email=user_id, data=users[user_id])
    return None


# ── 로그인 폼 ────────────────────────────────────────────────

class LoginForm(FlaskForm):
    email = StringField("이메일", validators=[DataRequired(), Email()])
    password = PasswordField("비밀번호", validators=[DataRequired()])
    remember = BooleanField("로그인 상태 유지 (30일)")


# ── 라우트 ──────────────────────────────────────────────────

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    form = LoginForm()
    error = None

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        password = form.password.data
        remember = form.remember.data

        locked_for = is_locked(email)
        if locked_for > 0:
            mins = locked_for // 60 + 1
            error = f"로그인 실패 5회 초과. 약 {mins}분 후 다시 시도하세요."
            log_event("login_failed", email=email, details={"reason": "locked", "lockout_seconds": locked_for})
        else:
            users = load_users()
            user_data = users.get(email)
            if user_data and verify_password(password, user_data["password_hash"]):
                clear_failures(email)
                user = User(email=email, data=user_data)
                login_user(user, remember=remember)
                sid = new_session_id()
                session["sid"] = sid
                session["login_time"] = datetime.utcnow().isoformat()
                log_event("login", email=email,
                          details={"remember": bool(remember),
                                   "is_admin": bool(user_data.get("is_admin"))},
                          session_id=sid)
                next_page = request.args.get("next") or url_for("index")
                if not next_page.startswith("/"):
                    next_page = url_for("index")
                return redirect(next_page)
            else:
                record_failure(email)
                attempts_left = MAX_ATTEMPTS - len(_FAILED_ATTEMPTS.get(email, []))
                if attempts_left <= 0:
                    error = "로그인 실패 5회 초과. 10분 후 다시 시도하세요."
                    log_event("login_failed", email=email, details={"reason": "locked_now"})
                else:
                    error = f"이메일 또는 비밀번호가 일치하지 않습니다. (남은 시도: {attempts_left}회)"
                    log_event("login_failed", email=email,
                              details={"reason": "bad_password", "attempts_left": attempts_left})

    return render_template("login.html", form=form, error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    # 세션 기간 계산 (login_time이 session에 있으면)
    email = current_user.email if current_user.is_authenticated else ""
    sid = session.get("sid")
    login_time_iso = session.get("login_time")
    duration_seconds = None
    if login_time_iso:
        try:
            lt = datetime.fromisoformat(login_time_iso)
            duration_seconds = int((datetime.utcnow() - lt).total_seconds())
        except Exception:
            pass

    log_event("logout", email=email,
              details={"duration_seconds": duration_seconds} if duration_seconds is not None else None,
              session_id=sid)

    logout_user()
    session.pop("sid", None)
    session.pop("login_time", None)
    return redirect(url_for("auth.login"))
