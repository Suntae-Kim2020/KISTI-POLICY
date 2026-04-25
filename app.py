#!/usr/bin/env python3
"""
KISTI Policy 분석 대시보드 — Flask 서버
포트 5002에서 data_cache.json을 서빙한다.
"""
import base64
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.request
from datetime import timedelta
from pathlib import Path

import io

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for
from flask_compress import Compress
from flask_login import LoginManager, current_user, login_required
from flask_wtf.csrf import CSRFProtect

from admin import admin_bp
from auth import auth_bp, load_user_by_id


def _get_flask_secret_key():
    key = os.environ.get("FLASK_SECRET_KEY")
    if key:
        return key
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        project = os.environ.get("GCP_PROJECT", "ailibrary-kisti")
        secret_name = os.environ.get("FLASK_SECRET_NAME", "flask-secret-key")
        name = f"projects/{project}/secrets/{secret_name}/versions/latest"
        return client.access_secret_version(request={"name": name}).payload.data.decode("utf-8")
    except Exception:
        return secrets.token_hex(32)


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB (일괄 저장용)
app.config["SECRET_KEY"] = _get_flask_secret_key()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["REMEMBER_COOKIE_DURATION"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("K_SERVICE"):  # Cloud Run에서만 Secure 쿠키 강제
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["REMEMBER_COOKIE_SECURE"] = True
app.config["COMPRESS_MIMETYPES"] = [
    "text/html", "text/css", "text/javascript",
    "application/javascript", "application/json",
]
app.config["COMPRESS_LEVEL"] = 6
app.config["COMPRESS_MIN_SIZE"] = 500
app.config["WTF_CSRF_TIME_LIMIT"] = None
Compress(app)

csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "로그인이 필요합니다."


@login_manager.user_loader
def _load_user(user_id):
    return load_user_by_id(user_id)


app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
# API POST 라우트는 CSRF 예외 (프론트에서 토큰 없이 호출)
csrf.exempt(auth_bp)


def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


DATA_DIR = Path(__file__).parent
EXCLUSIONS_PATH = DATA_DIR / "exclusions.json"
KISTEP_BASE = Path(os.environ.get("KISTEP_BASE", "/Users/kimsuntae/KISTEP"))
_caches = {}  # 버전별 캐시: {version_key: data_dict}


def _load_cache(version=None):
    """버전별 데이터 캐시 로드. version=None이면 기본 data_cache.json."""
    if version:
        key = version
        path = DATA_DIR / f"data_cache_{version}.json"
    else:
        key = "__default__"
        path = DATA_DIR / "data_cache.json"

    if key not in _caches:
        if path.exists():
            _caches[key] = json.loads(path.read_text(encoding="utf-8"))
        else:
            _caches[key] = {"error": f"{path.name} not found. Run compute.py first."}
    return _caches[key]


@app.route("/")
@login_required
def index():
    return render_template("dashboard.html", current_user=current_user)


@app.route("/api/versions")
@login_required
def api_versions():
    """생성된 캐시 + 소스 데이터 버전 통합 목록 반환."""
    # 1) 이미 생성된 data_cache_*.json
    cached = {}
    for f in sorted(DATA_DIR.glob("data_cache_*.json")):
        m = re.match(r"data_cache_(.+)\.json$", f.name)
        if not m:
            continue
        ver = m.group(1)
        data = _load_cache(ver)
        meta = data.get("_meta", {})
        cached[ver] = {
            "version": ver,
            "period": meta.get("analysis_period", ""),
            "start_year": meta.get("start_year"),
            "end_year": meta.get("end_year"),
            "generated_at": meta.get("generated_at", ""),
            "cached": True,
        }

    # 2) KISTEP/generated/ 소스 데이터 스캔
    gen_dir = KISTEP_BASE / "generated"
    if gen_dir.exists():
        key_files = ["wos_data.pkl", "wos_institutions.pkl", "jcr_jif.pkl",
                     "esi_journal_map.pkl"]
        master_dir = gen_dir / "master"
        for d in sorted(gen_dir.iterdir()):
            if not d.is_dir() or d.name == "master":
                continue
            ver = d.name
            # 파일 존재 확인 (직접 또는 master fallback)
            found = []
            for fname in key_files:
                if (d / fname).exists():
                    found.append(fname)
                elif master_dir.exists() and (master_dir / fname).exists():
                    found.append(fname + " (master)")
            complete = len(found) == len(key_files)
            if ver not in cached:
                cached[ver] = {
                    "version": ver,
                    "period": "",
                    "start_year": None,
                    "end_year": None,
                    "generated_at": "",
                    "cached": False,
                    "source_complete": complete,
                    "source_files": found,
                }
            else:
                cached[ver]["source_complete"] = complete
                cached[ver]["source_files"] = found

    return jsonify(sorted(cached.values(), key=lambda v: v["version"]))


@app.route("/api/compute", methods=["POST"])
@admin_required
@csrf.exempt
def api_compute():
    """compute.py 실행하여 데이터 캐시 생성. ~2분 소요."""
    data = request.get_json(force=True)
    version = data.get("version")
    start_year = data.get("start_year", 2008)
    end_year = data.get("end_year", 2024)

    if not version:
        return jsonify({"ok": False, "error": "version 필수"}), 400

    cmd = [
        sys.executable, str(DATA_DIR / "compute.py"),
        "--version", str(version),
        "--start-year", str(start_year),
        "--end-year", str(end_year),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=str(DATA_DIR),
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "시간 초과 (10분)"}), 504

    if result.returncode == 0:
        # 캐시 무효화
        for k in [version, "__default__"]:
            _caches.pop(k, None)
        return jsonify({"ok": True, "output": result.stdout})
    else:
        return jsonify({
            "ok": False,
            "error": result.stderr or result.stdout or "알 수 없는 오류",
        }), 500


@app.route("/api/export", methods=["POST"])
@login_required
@csrf.exempt
def api_export():
    """(사용되지 않음) 일괄 저장은 클라이언트 JSZip으로 이전됨."""
    return jsonify({"ok": False, "error": "클라이언트 ZIP 방식으로 이전되었습니다."}), 410


def _removed_api_export():
    """원본 코드 보관 (Cloud Run 파일시스템 불영속으로 미사용)."""
    data = request.get_json(force=True)
    folder_name = data.get("folder", "export")
    items = data.get("items", [])

    if not items:
        return jsonify({"ok": False, "error": "저장할 항목이 없습니다."}), 400

    out_dir = DATA_DIR / "generated" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    errors = []
    for item in items:
        name = item.get("name", "unknown")
        typ = item.get("type", "")
        payload = item.get("data", "")

        # 파일명 안전 처리
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)

        try:
            if typ == "png":
                # base64 데이터 URI에서 헤더 제거
                if "," in payload:
                    payload = payload.split(",", 1)[1]
                raw = base64.b64decode(payload)
                (out_dir / safe_name).write_bytes(raw)
                saved += 1
            elif typ == "csv":
                # UTF-8 BOM + CSV 텍스트
                (out_dir / safe_name).write_text(
                    "\ufeff" + payload, encoding="utf-8"
                )
                saved += 1
            else:
                errors.append(f"알 수 없는 타입: {typ} ({name})")
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    return jsonify({
        "ok": True,
        "saved": saved,
        "errors": errors,
        "folder": str(out_dir),
    })


@app.route("/api/export-html", methods=["POST"])
@admin_required
@csrf.exempt
def api_export_html():
    """독립 실행 가능한 라이브차트 HTML 생성."""
    payload = request.get_json(force=True)
    version = payload.get("version")

    # 1. dashboard.html 읽기
    html_path = DATA_DIR / "templates" / "dashboard.html"
    if not html_path.exists():
        return jsonify({"ok": False, "error": "dashboard.html not found"}), 404
    html = html_path.read_text(encoding="utf-8")

    # 2. CDN JS 다운로드 + 로컬 캐시
    cdn_dir = DATA_DIR / "generated" / "cdn"
    cdn_dir.mkdir(parents=True, exist_ok=True)
    cdn_map = [
        ("chart.umd.min.js",
         "https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"),
        ("chartjs-plugin-datalabels.min.js",
         "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0/dist/"
         "chartjs-plugin-datalabels.min.js"),
    ]
    cdn_js = {}
    for fname, url in cdn_map:
        cached_path = cdn_dir / fname
        if cached_path.exists():
            cdn_js[fname] = cached_path.read_text(encoding="utf-8")
        else:
            try:
                resp = urllib.request.urlopen(url, timeout=30)
                js_text = resp.read().decode("utf-8")
                cached_path.write_text(js_text, encoding="utf-8")
                cdn_js[fname] = js_text
            except Exception as e:
                return jsonify({
                    "ok": False,
                    "error": f"CDN 다운로드 실패 ({fname}): {e}",
                }), 502

    # 3. data_cache 로딩
    cache_data = _load_cache(version)
    if "error" in cache_data:
        cache_data = _load_cache()
    if "error" in cache_data:
        return jsonify({"ok": False, "error": cache_data["error"]}), 400

    # 4. exclusions 로딩
    excl_data = _load_exclusions()

    # ── 5. HTML 문자열 치환 ──────────────────────────────────

    # (a) CDN <script src="..."> → <script>인라인</script>
    html = html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7'
        '/dist/chart.umd.min.js"></script>',
        '<script>/* chart.js 4.4.7 */\n'
        + cdn_js["chart.umd.min.js"] + '\n</script>',
    )
    html = html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels'
        '@2.2.0/dist/chartjs-plugin-datalabels.min.js"></script>',
        '<script>/* chartjs-plugin-datalabels 2.2.0 */\n'
        + cdn_js["chartjs-plugin-datalabels.min.js"] + '\n</script>',
    )

    # (b) 서버 의존 UI 제거
    #   - version select + label + status span
    html = html.replace('<label>데이터</label>', '')
    html = re.sub(
        r'<select id="versionSelect"[^>]*></select>', '', html)
    html = re.sub(
        r'<span class="ver-status"[^>]*></span>', '', html)
    #   - 생성 / 일괄저장 / 라이브차트 버튼
    html = re.sub(
        r'<button class="btn-generate"[^>]*>[^<]*</button>', '', html)
    html = html.replace(
        '<button onclick="exportAll()">일괄 저장</button>', '')
    html = html.replace(
        '<button onclick="exportHTML()">라이브차트 생성</button>', '')
    #   - 논문 관리 nav-item
    html = re.sub(
        r'\s*<div class="section-title">관리</div>'
        r'\s*<a class="nav-item" data-page="papers"[^>]*>논문 관리</a>',
        '', html,
    )

    # (c) init() boot → standalone boot (인라인 데이터 주입)
    #     요청에 기간이 포함되면 해당 기간으로 초기화
    start_year = payload.get("start_year")
    end_year = payload.get("end_year")
    meta = cache_data.get("_meta", {})
    if not start_year:
        start_year = meta.get("start_year", 2008)
    if not end_year:
        end_year = meta.get("end_year", 2024)

    data_json = json.dumps(
        cache_data, ensure_ascii=False).replace('</', '<\\/')
    excl_json = json.dumps(
        excl_data, ensure_ascii=False).replace('</', '<\\/')

    need_recompute = (
        start_year != meta.get("start_year")
        or end_year != meta.get("end_year")
    )

    boot_code = '\n'.join([
        '// Standalone Boot',
        'DATA = ' + data_json + ';',
        'var _excl = ' + excl_json + ';',
        'EXCLUSIONS.kisti = new Set(_excl.kisti || []);',
        'EXCLUSIONS.induced = new Set(_excl.induced || []);',
        'EXCLUSIONS.kbsi = new Set(_excl.kbsi || []);',
        'EXCLUSIONS.kbsi_induced = new Set(_excl.kbsi_induced || []);',
        'EXCLUSIONS.ibs = new Set(_excl.ibs || []);',
        'EXCLUSIONS.ibs_induced = new Set(_excl.ibs_induced || []);',
        'EXCLUSIONS.pal_induced = new Set(_excl.pal_induced || []);',
        '_applyDataGlobals();',
        # PERIOD를 _applyDataGlobals() 이후에 설정해야 덮어써지지 않음
        f'PERIOD.start = {start_year};',
        f'PERIOD.end = {end_year};',
        f"document.getElementById('startYearInput').value = {start_year};",
        f"document.getElementById('endYearInput').value = {end_year};",
        "document.getElementById('headerSubtitle').textContent = "
        f"'KISTI\\xb7KBSI\\xb7IBS\\xb7PAL 논문 성과 및 인프라 유발 효과 비교 분석 ({start_year}-{end_year})"
        f" \\u2014 데이터 v' + DATA._meta.data_version;",
        # 기간 범위 제한: 입력 min/max + applyPeriod 래핑
        f'var _EMIN={start_year}, _EMAX={end_year};',
        "var _si=document.getElementById('startYearInput'),"
        " _ei=document.getElementById('endYearInput');",
        '_si.min=_EMIN; _si.max=_EMAX; _ei.min=_EMIN; _ei.max=_EMAX;',
        '_si.onkeydown=_ei.onkeydown=function(e){'
        "if(e.key!=='Tab')e.preventDefault();};",
        "_si.style.caretColor='transparent'; _ei.style.caretColor='transparent';",
        "_si.style.cursor='default'; _ei.style.cursor='default';",
        'var _origApplyPeriod = applyPeriod;',
        'applyPeriod = function(){',
        '  var s=parseInt(_si.value), e=parseInt(_ei.value);',
        '  if(s<_EMIN){s=_EMIN;_si.value=s;}',
        '  if(e>_EMAX){e=_EMAX;_ei.value=e;}',
        '  if(s>_EMAX){s=_EMAX;_si.value=s;}',
        '  if(e<_EMIN){e=_EMIN;_ei.value=e;}',
        '  _origApplyPeriod();',
        '};',
        "document.getElementById('globalLoading').style.display = 'none';",
        'buildPages();',
        'recomputeAllStats(PERIOD.start, PERIOD.end);',
        "showPage('overview');",
    ])
    html = html.replace('init();\n</script>', boot_code + '\n</script>')

    # 6. 다운로드 응답 (Cloud Run 파일시스템 불영속이므로 스트리밍 반환)
    period = f"{start_year}-{end_year}"
    ver = version or meta.get("data_version", "unknown")
    filename = f"dashboard_v{ver}_{period}.html"

    encoded = html.encode("utf-8")

    # 감사 로그
    try:
        from audit import log_event
        log_event("download_html",
                  email=current_user.email if current_user.is_authenticated else "",
                  details={
                      "filename": filename,
                      "size_bytes": len(encoded),
                      "size_mb": round(len(encoded) / 1024 / 1024, 2),
                      "data_version": ver,
                      "period": period,
                  })
    except Exception:
        pass

    buf = io.BytesIO(encoded)
    return send_file(
        buf, mimetype="text/html; charset=utf-8",
        as_attachment=True, download_name=filename,
    )


@app.route("/api/data")
@login_required
def api_data():
    version = request.args.get("version")
    return jsonify(_load_cache(version))


def _load_exclusions():
    defaults = {"kisti": [], "induced": [], "kbsi": [], "kbsi_induced": [], "ibs": [], "ibs_induced": [], "pal_induced": []}
    if EXCLUSIONS_PATH.exists():
        data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
        for k in defaults:
            if k not in data:
                data[k] = []
        return data
    return defaults


@app.route("/api/audit/zip", methods=["POST"])
@login_required
@csrf.exempt
def api_audit_zip():
    """ZIP 일괄저장 완료 시 클라이언트가 호출하는 로그 전용 엔드포인트."""
    from audit import log_event
    data = request.get_json(force=True) or {}
    log_event("download_zip",
              email=current_user.email if current_user.is_authenticated else "",
              details={
                  "filename": data.get("filename", ""),
                  "file_count": int(data.get("file_count", 0)),
                  "size_mb": float(data.get("size_mb", 0)),
                  "data_version": data.get("data_version", ""),
                  "period": data.get("period", ""),
              })
    return jsonify({"ok": True})


@app.route("/api/exclusions", methods=["GET"])
@login_required
def get_exclusions():
    return jsonify(_load_exclusions())


@app.route("/api/exclusions", methods=["POST"])
@admin_required
@csrf.exempt
def save_exclusions():
    data = request.get_json(force=True)
    out = {
        "kisti": data.get("kisti", []),
        "induced": data.get("induced", []),
        "kbsi": data.get("kbsi", []),
        "kbsi_induced": data.get("kbsi_induced", []),
        "ibs": data.get("ibs", []),
        "ibs_induced": data.get("ibs_induced", []),
        "pal_induced": data.get("pal_induced", []),
    }
    EXCLUSIONS_PATH.write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("Loading data cache...")
    _load_cache()
    default_data = _caches.get("__default__", {})
    if "error" in default_data:
        print(f"WARNING: {default_data['error']}")
    else:
        s = default_data.get("summary", {})
        print(f"  KISTI 논문: {s.get('kisti_papers', '?'):,}건")
        print(f"  KISTI 유발논문: {s.get('induced_papers', '?'):,}건")
        print(f"  KBSI 논문: {s.get('kbsi_papers', '?'):,}건")
        print(f"  KBSI 유발논문: {s.get('kbsi_induced_papers', '?'):,}건")
        print(f"  IBS 논문: {s.get('ibs_papers', '?'):,}건")
        print(f"  IBS 유발논문: {s.get('ibs_induced_papers', '?'):,}건")
        print(f"  PAL 유발논문: {s.get('pal_induced_papers', '?'):,}건")
    port = int(os.environ.get("PORT", 5002))
    print(f"Starting KISTI Policy Dashboard on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
