"""
관리자 전용 사용자 관리 Blueprint
경로: /admin/users
"""
import secrets
import string
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField
from wtforms.validators import DataRequired, Email, Length

from auth import (
    _FAILED_ATTEMPTS,
    clear_failures,
    hash_password,
    load_users,
    save_users,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.before_request
@login_required
def _require_admin():
    if not getattr(current_user, "is_admin", False):
        abort(403)


class AddUserForm(FlaskForm):
    email = StringField("이메일", validators=[DataRequired(), Email()])
    name = StringField("이름", validators=[DataRequired(), Length(min=1, max=50)])
    is_admin = BooleanField("관리자")


def _random_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@admin_bp.route("/users")
def users_list():
    users = load_users()
    lockouts = {
        email: len(attempts)
        for email, attempts in _FAILED_ATTEMPTS.items() if attempts
    }
    form = AddUserForm()
    return render_template(
        "admin_users.html",
        users=sorted(users.items()),
        lockouts=lockouts,
        form=form,
        current_email=current_user.email,
    )


@admin_bp.route("/users/add", methods=["POST"])
def users_add():
    form = AddUserForm()
    if not form.validate_on_submit():
        errs = "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items())
        flash(f"입력 오류: {errs}", "error")
        return redirect(url_for("admin.users_list"))

    email = form.email.data.strip().lower()
    users = load_users(force_refresh=True)
    if email in users:
        flash(f"이미 존재하는 이메일: {email}", "error")
        return redirect(url_for("admin.users_list"))

    password = _random_password()
    users[email] = {
        "password_hash": hash_password(password),
        "name": form.name.data.strip(),
        "is_admin": bool(form.is_admin.data),
        "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    save_users(users)
    role = "관리자" if form.is_admin.data else "일반 사용자"
    flash(f"✅ {role} 추가: {email} | 임시 비밀번호: {password}", "password")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/delete", methods=["POST"])
def users_delete():
    email = request.form.get("email", "").strip().lower()
    if email == current_user.email:
        flash("자기 자신은 삭제할 수 없습니다.", "error")
        return redirect(url_for("admin.users_list"))

    users = load_users(force_refresh=True)
    if email not in users:
        flash(f"존재하지 않음: {email}", "error")
        return redirect(url_for("admin.users_list"))

    del users[email]
    save_users(users)
    clear_failures(email)
    flash(f"✅ 삭제: {email}", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/passwd", methods=["POST"])
def users_passwd():
    email = request.form.get("email", "").strip().lower()
    users = load_users(force_refresh=True)
    if email not in users:
        flash(f"존재하지 않음: {email}", "error")
        return redirect(url_for("admin.users_list"))

    password = _random_password()
    users[email]["password_hash"] = hash_password(password)
    save_users(users)
    clear_failures(email)
    flash(f"✅ 비밀번호 재설정: {email} | 새 임시 비밀번호: {password}", "password")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/toggle-admin", methods=["POST"])
def users_toggle_admin():
    email = request.form.get("email", "").strip().lower()
    if email == current_user.email:
        flash("자기 자신의 권한은 변경할 수 없습니다.", "error")
        return redirect(url_for("admin.users_list"))

    users = load_users(force_refresh=True)
    if email not in users:
        flash(f"존재하지 않음: {email}", "error")
        return redirect(url_for("admin.users_list"))

    users[email]["is_admin"] = not users[email].get("is_admin", False)
    save_users(users)
    role = "관리자" if users[email]["is_admin"] else "일반 사용자"
    flash(f"✅ {email} → {role}", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/unlock", methods=["POST"])
def users_unlock():
    email = request.form.get("email", "").strip().lower()
    clear_failures(email)
    flash(f"✅ 로그인 실패 카운터 초기화: {email}", "success")
    return redirect(url_for("admin.users_list"))
