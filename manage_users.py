#!/usr/bin/env python3
"""
사용자 관리 CLI — Secret Manager의 kisti-users JSON 조작

사용법:
  python3 manage_users.py list
  python3 manage_users.py add <email> [--admin] [--name "이름"]
  python3 manage_users.py remove <email>
  python3 manage_users.py passwd <email>
  python3 manage_users.py promote <email>      # 관리자로 승격
  python3 manage_users.py demote <email>       # 일반 사용자로
  python3 manage_users.py unlock <email>       # 로그인 잠금 해제는 앱에서만

환경변수:
  USERS_SECRET: 기본 "kisti-users"
  GCP_PROJECT:  기본 "ailibrary-kisti"
"""
import argparse
import getpass
import json
import os
import secrets
import string
import sys
from datetime import datetime

import bcrypt

USERS_SECRET = os.environ.get("USERS_SECRET", "kisti-users")
PROJECT_ID = os.environ.get("GCP_PROJECT", "ailibrary-kisti")


def _client():
    from google.cloud import secretmanager
    return secretmanager.SecretManagerServiceClient()


def _secret_exists():
    client = _client()
    try:
        client.get_secret(request={"name": f"projects/{PROJECT_ID}/secrets/{USERS_SECRET}"})
        return True
    except Exception:
        return False


def ensure_secret():
    if _secret_exists():
        return
    client = _client()
    print(f"Creating secret: {USERS_SECRET}")
    client.create_secret(
        request={
            "parent": f"projects/{PROJECT_ID}",
            "secret_id": USERS_SECRET,
            "secret": {"replication": {"automatic": {}}},
        }
    )


def load():
    client = _client()
    try:
        resp = client.access_secret_version(
            request={"name": f"projects/{PROJECT_ID}/secrets/{USERS_SECRET}/versions/latest"}
        )
        return json.loads(resp.payload.data.decode("utf-8"))
    except Exception:
        return {}


def save(users_dict):
    client = _client()
    payload = json.dumps(users_dict, ensure_ascii=False, indent=2).encode("utf-8")
    client.add_secret_version(
        request={
            "parent": f"projects/{PROJECT_ID}/secrets/{USERS_SECRET}",
            "payload": {"data": payload},
        }
    )


def hash_pw(plain):
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def prompt_password(confirm=True):
    while True:
        pw = getpass.getpass("비밀번호: ")
        if len(pw) < 8:
            print("  ⚠️ 8자 이상이어야 합니다.")
            continue
        if confirm:
            pw2 = getpass.getpass("비밀번호 확인: ")
            if pw != pw2:
                print("  ⚠️ 불일치. 다시 입력하세요.")
                continue
        return pw


def generate_password():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def cmd_list(args):
    users = load()
    if not users:
        print("등록된 사용자가 없습니다.")
        return
    print(f"\n{USERS_SECRET} — 총 {len(users)}명\n")
    print(f"{'역할':<6} {'이메일':<35} {'이름':<20} {'등록일'}")
    print("-" * 85)
    for email in sorted(users):
        u = users[email]
        role = "ADMIN" if u.get("is_admin") else "user"
        print(f"{role:<6} {email:<35} {u.get('name', ''):<20} {u.get('created_at', '')}")


def cmd_add(args):
    ensure_secret()
    users = load()
    email = args.email.strip().lower()
    if email in users:
        print(f"⚠️ 이미 존재: {email}")
        return 1

    if args.random_password:
        pw = generate_password()
        print(f"⚙️ 임시 비밀번호: {pw}")
        print("   (사용자에게 전달 후 변경 권고)")
    else:
        pw = prompt_password()

    users[email] = {
        "password_hash": hash_pw(pw),
        "name": args.name or email.split("@")[0],
        "is_admin": args.admin,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d"),
    }
    save(users)
    role = "관리자" if args.admin else "일반 사용자"
    print(f"✅ {role} 추가: {email}")


def cmd_remove(args):
    users = load()
    email = args.email.strip().lower()
    if email not in users:
        print(f"⚠️ 없음: {email}")
        return 1
    del users[email]
    save(users)
    print(f"✅ 삭제: {email}")


def cmd_passwd(args):
    users = load()
    email = args.email.strip().lower()
    if email not in users:
        print(f"⚠️ 없음: {email}")
        return 1
    pw = prompt_password()
    users[email]["password_hash"] = hash_pw(pw)
    save(users)
    print(f"✅ 비밀번호 변경: {email}")


def cmd_promote(args):
    users = load()
    email = args.email.strip().lower()
    if email not in users:
        print(f"⚠️ 없음: {email}")
        return 1
    users[email]["is_admin"] = True
    save(users)
    print(f"✅ 관리자로 승격: {email}")


def cmd_demote(args):
    users = load()
    email = args.email.strip().lower()
    if email not in users:
        print(f"⚠️ 없음: {email}")
        return 1
    users[email]["is_admin"] = False
    save(users)
    print(f"✅ 일반 사용자로 강등: {email}")


def main():
    p = argparse.ArgumentParser(description="KISTI Policy 사용자 관리 CLI")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list", help="사용자 목록")

    add_p = sub.add_parser("add", help="사용자 추가")
    add_p.add_argument("email")
    add_p.add_argument("--admin", action="store_true", help="관리자로 등록")
    add_p.add_argument("--name", help="표시 이름")
    add_p.add_argument("--random-password", action="store_true",
                       help="임시 비밀번호 자동 생성")

    rm_p = sub.add_parser("remove", help="사용자 삭제")
    rm_p.add_argument("email")

    pw_p = sub.add_parser("passwd", help="비밀번호 변경")
    pw_p.add_argument("email")

    pr_p = sub.add_parser("promote", help="관리자로 승격")
    pr_p.add_argument("email")

    dm_p = sub.add_parser("demote", help="일반 사용자로 강등")
    dm_p.add_argument("email")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return 1

    fn = {
        "list": cmd_list,
        "add": cmd_add,
        "remove": cmd_remove,
        "passwd": cmd_passwd,
        "promote": cmd_promote,
        "demote": cmd_demote,
    }[args.cmd]

    try:
        return fn(args) or 0
    except KeyboardInterrupt:
        print("\n중단됨.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
