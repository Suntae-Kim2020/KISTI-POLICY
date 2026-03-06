#!/usr/bin/env python3
"""
KISTI Policy 분석 대시보드 — Flask 서버
포트 5002에서 data_cache.json을 서빙한다.
"""
import base64
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB (일괄 저장용)

DATA_DIR = Path(__file__).parent
EXCLUSIONS_PATH = DATA_DIR / "exclusions.json"
KISTEP_BASE = Path("/Users/kimsuntae/KISTEP")
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
def index():
    return render_template("dashboard.html")


@app.route("/api/versions")
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
def api_export():
    """차트(PNG)와 테이블(CSV)을 서버 폴더에 일괄 저장."""
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
        '_applyDataGlobals();',
        # PERIOD를 _applyDataGlobals() 이후에 설정해야 덮어써지지 않음
        f'PERIOD.start = {start_year};',
        f'PERIOD.end = {end_year};',
        f"document.getElementById('startYearInput').value = {start_year};",
        f"document.getElementById('endYearInput').value = {end_year};",
        "document.getElementById('headerSubtitle').textContent = "
        f"'KISTI\\xb7KBSI 논문 성과 및 인프라 유발 효과 비교 분석 ({start_year}-{end_year})"
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

    # 6. 저장
    period = f"{start_year}-{end_year}"
    ver = version or meta.get("data_version", "unknown")

    out_dir = DATA_DIR / "generated" / "html"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dashboard_v{ver}_{period}.html"
    out_path.write_text(html, encoding="utf-8")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    return jsonify({
        "ok": True,
        "path": str(out_path),
        "size_mb": round(size_mb, 1),
    })


@app.route("/api/data")
def api_data():
    version = request.args.get("version")
    return jsonify(_load_cache(version))


def _load_exclusions():
    defaults = {"kisti": [], "induced": [], "kbsi": [], "kbsi_induced": []}
    if EXCLUSIONS_PATH.exists():
        data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
        for k in defaults:
            if k not in data:
                data[k] = []
        return data
    return defaults


@app.route("/api/exclusions", methods=["GET"])
def get_exclusions():
    return jsonify(_load_exclusions())


@app.route("/api/exclusions", methods=["POST"])
def save_exclusions():
    data = request.get_json(force=True)
    out = {
        "kisti": data.get("kisti", []),
        "induced": data.get("induced", []),
        "kbsi": data.get("kbsi", []),
        "kbsi_induced": data.get("kbsi_induced", []),
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
    print("Starting KISTI Policy Dashboard on http://localhost:5002")
    app.run(host="0.0.0.0", port=5002, debug=False)
