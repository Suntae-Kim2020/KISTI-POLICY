#!/usr/bin/env python3
"""
KISTI Policy 분석 대시보드 — 데이터 전처리 스크립트
pickle 로딩 → KISTI 논문/유발논문 분류 → 섹션별 통계 → data_cache.json 생성
"""
import argparse
import csv
import json
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DEFAULT_BASE = Path("/Users/kimsuntae/KISTEP")
DEFAULT_OUT = Path(__file__).parent / "data_cache.json"


# ═══════════════════════════════════════════════════════════
# 실행 설정 (RunConfig)
# ═══════════════════════════════════════════════════════════
@dataclass
class RunConfig:
    data_version: str = "2024"
    start_year: int = 2008
    end_year: int = 2024
    base_path: Path = field(default_factory=lambda: DEFAULT_BASE)
    snapshot: Optional[str] = None
    output: Path = field(default_factory=lambda: DEFAULT_OUT)

    @property
    def years(self) -> List[int]:
        return list(range(self.start_year, self.end_year + 1))

    @property
    def num_years(self) -> int:
        return self.end_year - self.start_year + 1

    @property
    def period_str(self) -> str:
        return f"{self.start_year}-{self.end_year}"


def resolve_file(filename: str, config: RunConfig) -> Path:
    """파일 경로 해석 — 우선순위: snapshot → generated/{version}/ → generated/master/ → 루트"""
    candidates = []
    if config.snapshot:
        candidates.append(config.base_path / "generated" / config.data_version
                          / "snapshots" / config.snapshot / filename)
    candidates.append(config.base_path / "generated" / config.data_version / filename)
    candidates.append(config.base_path / "generated" / "master" / filename)
    candidates.append(config.base_path / filename)
    for p in candidates:
        if p.exists() and not p.is_symlink() or (p.is_symlink() and p.resolve().exists()):
            return p
    tried = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(f"{filename} 을 찾을 수 없습니다.\n검색 경로:\n  {tried}")


def discover_versions(base_path: Path) -> list[dict]:
    """generated/ 하위 데이터 버전 스캔"""
    gen_dir = base_path / "generated"
    if not gen_dir.exists():
        return []
    versions = []
    for d in sorted(gen_dir.iterdir()):
        if not d.is_dir() or d.name == "master":
            continue
        key_files = ["wos_data.pkl", "wos_institutions.pkl", "jcr_jif.pkl", "esi_journal_map.pkl"]
        # 직접 파일 또는 master fallback 확인
        found = []
        for f in key_files:
            if (d / f).exists():
                found.append(f)
            elif (gen_dir / "master" / f).exists():
                found.append(f + " (master)")
        # 스냅샷 목록
        snap_dir = d / "snapshots"
        snapshots = []
        if snap_dir.exists():
            snapshots = sorted([s.name for s in snap_dir.iterdir() if s.is_dir()])
        versions.append({
            "version": d.name,
            "files": found,
            "complete": len(found) == len(key_files),
            "snapshots": snapshots,
        })
    return versions


def interactive_config(base_path: Path) -> RunConfig:
    """인터랙티브 모드: 버전 선택 → 분석 기간 입력"""
    versions = discover_versions(base_path)
    if not versions:
        print("⚠ generated/ 하위에 데이터 버전이 없습니다.")
        sys.exit(1)

    print("\n사용 가능한 데이터 버전:")
    for i, v in enumerate(versions, 1):
        status = "✓" if v["complete"] else "△"
        snap_info = f" (스냅샷 {len(v['snapshots'])}개)" if v["snapshots"] else ""
        print(f"  [{i}] {v['version']} {status}{snap_info}")
    print()

    while True:
        choice = input(f"버전 선택 [1-{len(versions)}, 기본=1]: ").strip()
        if not choice:
            idx = 0
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(versions):
                break
        except ValueError:
            pass
        print("  잘못된 입력입니다.")

    ver = versions[idx]
    config = RunConfig(data_version=ver["version"], base_path=base_path)

    # 스냅샷 선택
    if ver["snapshots"]:
        print(f"\n스냅샷 목록 ({ver['version']}):")
        print(f"  [0] 스냅샷 미사용 (기본)")
        for i, s in enumerate(ver["snapshots"], 1):
            print(f"  [{i}] {s}")
        snap_choice = input(f"스냅샷 선택 [0-{len(ver['snapshots'])}, 기본=0]: ").strip()
        if snap_choice:
            try:
                si = int(snap_choice)
                if 1 <= si <= len(ver["snapshots"]):
                    config.snapshot = ver["snapshots"][si - 1]
            except ValueError:
                pass

    # 분석 기간
    period = input(f"\n분석 기간 [시작-끝, 기본={config.start_year}-{config.end_year}]: ").strip()
    if period:
        try:
            parts = period.split("-")
            config.start_year = int(parts[0])
            config.end_year = int(parts[1])
        except (ValueError, IndexError):
            print("  잘못된 형식. 기본값 사용.")

    return config


def parse_args() -> Optional[RunConfig]:
    """CLI 인자 파싱. 인자 없으면 None (인터랙티브 모드 진입)."""
    parser = argparse.ArgumentParser(description="KISTI Policy 분석 데이터 생성")
    parser.add_argument("--version", type=str, help="데이터 버전 (예: 2024, 2025)")
    parser.add_argument("--start-year", type=int, default=2008, help="분석 시작 연도 (기본: 2008)")
    parser.add_argument("--end-year", type=int, default=2024, help="분석 종료 연도 (기본: 2024)")
    parser.add_argument("--snapshot", type=str, default=None, help="스냅샷 ID (예: 20260306_081605)")
    parser.add_argument("--base", type=str, default=str(DEFAULT_BASE), help="KISTEP 루트 경로")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT), help="출력 파일 경로")
    parser.add_argument("--list-versions", action="store_true", help="사용 가능한 버전 목록 표시 후 종료")

    # 인자가 없으면 None 반환 → 인터랙티브
    if len(sys.argv) == 1:
        return None

    args = parser.parse_args()
    base = Path(args.base)

    if args.list_versions:
        versions = discover_versions(base)
        if not versions:
            print("데이터 버전 없음")
        else:
            print(f"\n사용 가능한 데이터 버전 ({base / 'generated'}):")
            for v in versions:
                status = "✓ 완전" if v["complete"] else "△ 불완전"
                snap = f", 스냅샷: {', '.join(v['snapshots'])}" if v["snapshots"] else ""
                print(f"  {v['version']} [{status}]{snap}")
                for f in v["files"]:
                    print(f"    - {f}")
        sys.exit(0)

    if not args.version:
        parser.error("--version 필수 (또는 인자 없이 실행하여 인터랙티브 모드 사용)")

    return RunConfig(
        data_version=args.version,
        start_year=args.start_year,
        end_year=args.end_year,
        base_path=base,
        snapshot=args.snapshot,
        output=Path(args.output),
    )

KISTI_ORG_ALIAS = "KOREA INST SCI & TECHNOL INFORMAT"
KBSI_ORG_ALIAS = "KOREA BASIC SCI INST"
IBS_ORG_ALIAS = "INST BASIC SCI KOREA"

ESI_22_FIELDS = [
    "Agricultural Sciences", "Biology & Biochemistry", "Chemistry",
    "Clinical Medicine", "Computer Science", "Economics & Business",
    "Engineering", "Environment Ecology", "Geosciences", "Immunology",
    "Materials Science", "Mathematics", "Microbiology",
    "Molecular Biology & Genetics", "Multidisciplinary",
    "Neuroscience & Behavior", "Pharmacology & Toxicology", "Physics",
    "Plant & Animal Science", "Psychiatry Psychology",
    "Social Sciences, general", "Space Science",
]

INST_TYPE_7_ORDER = ["대학", "정부부처", "출연연구소", "국공립연구소", "기업", "병원", "기타"]

# ── ORG_ALIAS_KR (top institutions only for display) ──
ORG_ALIAS_KR = {
    "SEOUL NATL UNIV": "서울대학교", "YONSEI UNIV": "연세대학교",
    "KOREA UNIV": "고려대학교", "SUNGKYUNKWAN UNIV": "성균관대학교",
    "HANYANG UNIV": "한양대학교", "KAIST": "카이스트", "POSTECH": "포스텍",
    "KYUNG HEE UNIV": "경희대학교", "EWHA WOMANS UNIV": "이화여자대학교",
    "SOGANG UNIV": "서강대학교", "CHUNG ANG UNIV": "중앙대학교",
    "KYUNGPOOK NATL UNIV": "경북대학교", "PUSAN NATL UNIV": "부산대학교",
    "CHONNAM NATL UNIV": "전남대학교", "JEONBUK NATL UNIV": "전북대학교",
    "CHUNGNAM NATL UNIV": "충남대학교", "CHUNGBUK NATL UNIV": "충북대학교",
    "KANGWON NATL UNIV": "강원대학교", "GYEONGSANG NATL UNIV": "경상국립대학교",
    "SEJONG UNIV": "세종대학교", "KONKUK UNIV": "건국대학교",
    "DONGGUK UNIV": "동국대학교", "INHA UNIV": "인하대학교",
    "AJOU UNIV": "아주대학교", "CATHOLIC UNIV KOREA": "가톨릭대학교",
    "DGIST": "대구경북과학기술원", "GIST": "광주과학기술원",
    "ULSAN NATL INST SCI TECHNOL": "울산과학기술원",
    "INST BASIC SCI KOREA": "기초과학연구원(IBS)",
    # 출연연
    "KOREA INST SCI & TECHNOL": "한국과학기술연구원(KIST)",
    "KOREA RES INST BIOSCI & BIOTECHNOL": "한국생명공학연구원(KRIBB)",
    "KOREA RES INST CHEM TECHNOL": "한국화학연구원(KRICT)",
    "KOREA RES INST STAND & SCI": "한국표준과학연구원(KRISS)",
    "KOREA ATOM ENERGY RES INST": "한국원자력연구원(KAERI)",
    "KOREA BASIC SCI INST": "한국기초과학지원연구원(KBSI)",
    "KOREA INST OCEAN SCI & TECHNOL": "한국해양과학기술원(KIOST)",
    "KOREA INST GEOSCI & MINERAL RES": "한국지질자원연구원(KIGAM)",
    "KOREA INST MACHINERY & MAT": "한국기계연구원(KIMM)",
    "KOREA INST MAT SCI": "재료연구원(KIMS)",
    "KOREA INST IND TECHNOL": "한국생산기술연구원(KITECH)",
    "KOREA FOOD RES INST": "한국식품연구원(KFRI)",
    "KOREA INST ENERGY RES": "한국에너지기술연구원(KIER)",
    "KOREA ASTRON & SPACE INST": "한국천문연구원(KASI)",
    "KOREA ELECTROTECHNOL RES INST": "한국전기연구원(KERI)",
    "KOREA INST CERAM ENGN TECHNOL": "한국세라믹기술원(KICET)",
    "KOREA INST SCI & TECHNOL INFORMAT": "한국과학기술정보연구원(KISTI)",
    "ETRI": "한국전자통신연구원(ETRI)",
    "KOREA BRAIN RES INST": "한국뇌연구원(KBRI)",
    "KOREA INST FUS ENENRY": "한국핵융합에너지연구원(KFE)",
    "KOREA RAILROAD RES INST": "한국철도기술연구원(KRRI)",
    "KOREA AEROSP RES INST": "한국항공우주연구원(KARI)",
    # 기업
    "SAMSUNG ELECT CO LTD": "삼성전자", "LG CHEM LTD": "LG화학",
    "LG ELECTRONIC INC": "LG전자", "HYUNDAI MOTOR GRP": "현대자동차그룹",
    "SK HYNIX INC": "SK하이닉스", "POSCO": "포스코",
    # 병원
    "SEOUL NATL UNIV HOSP": "서울대병원",
    "SUNGKYUNKWAN UNIV SAMSUNG MED CTR": "성균관대 삼성서울병원",
    "UNIV ULSAN ASAN MED CTR": "울산대 서울아산병원",
    "YONSEI UNIV SEVERANCE HOSP": "연세대 세브란스병원",
    # 정부
    "KOREA DIS CONTROL & PREVENT AGCY": "질병관리청",
    "NATL CANC CTR": "국립암센터", "RDA": "농촌진흥청", "ADD": "국방과학연구소(ADD)",
    "NATL INST ENVIRONM RES": "국립환경과학원",
    "NATL INST FOREST SCI": "국립산림과학원",
}

_GOVT_TO_NATL_RESEARCH = {
    "ANIM PLANT QUARANTINE AGCY", "NATL INST FOREST SCI",
    "NATL INST ENVIRONM RES", "NATL INST FISHRIES SCI",
    "NATL INST ECOL", "NATL INST METEOROL SCI KMA",
    "KOREA NATL INST HLTH", "NATL FORENS SERV",
    "NATL INST BIOL RESOURCES", "NATL AGR PROD QUAL MANAGEMENT SERV",
    "KOREA NATL ARBORETUM", "NATL INST FOOD DRUG SAFETY EVALUAT",
    "NATL RES INST CULTURAL HERITAGE", "NATL FIRE RES INST",
    "NATL DISASTER MANAGEMENT INST", "NATL SCI MUSEUM",
    "NATL MUSEUM MODERN & CONTEMPORARY ART", "KOREA NATL PARK SERV",
    "KOREA AGCY TECHNOL STAND", "NATL RADIO RESEARCH AGENCY",
    "NATL METEOROL SATELLITE CTR",
    "NATL INST WILDLIFE DIS CONTROL & PREVENT",
    "KOREA SEED VARIETY SERV", "NATL MUSEUM KOREA",
    "NATL GEOG INFORMAT INST KOREA",
    "NATL FISHERY PROD QUAL MANAGEMENT SERV FIQ",
    "KOREA HYDROG & OCEANOG ADM", "NATL INST CHEM SAFELY",
    "NATL FOREST SEED & VARIETY CTR", "NATL QUARANTINE STN",
    "NATL RES FDN KOREA", "KOREA ENVIRONM IND TECH INST",
    "KOREA EVALUAT INST IND TECHNOL",
    "NATL RES INST MARITIME CULTURAL HERITAGE",
    "NATL ARCHIVES KOREA", "STAT RES INST",
    "NATL AIR EMISS INVENTORY & RES CTR",
    "SOFTWARE POLICY & RES INST SPRI",
    "INST INFORMAT COMMUN TECHNOL PLAN EVALUAT",
    "KOREA INST PLANNING & EVALUAT TECHNOL FOOD AGR FO",
    "KOREA INST ADV TECHNOL", "GWACHEON NATL SCI MUSEUM",
    "GREENHOUSE GAS INVERTORY & RES CTR KOREA",
    "KOREA FOREST WELF INST",
    "NATL INST ENVIRONM HUMAN RESOURCE DEV",
    "NATL FOLK MUSEUM KOREA", "NATL INST KOREAN HIST",
    "NATL MILYANG METEOROL SCI MUSEUM", "SEOUL NATL SCI MUSEUM",
    "NATL INTANGIBLE CULTURAL HERITAGE",
    "NATL INST ORGAN TISSUE BLOOD MANAGN",
    "NATL INST INFECT DIS", "OSONG HLTH TECHNOL ADM COMPLEX",
    "MOKPO MARINE FOOD IND RES CTR",
    "NATL CIVIL DEF & DISASTER MANAGEMENT TRAINING INST",
}

INFRA_KEYWORDS = {
    "KSC/NURION": ["KSC-", "NURION"],
    "KREONET": ["KREONET"],
    "EDISON": ["EDISON"],
    "PLSI/KIAF": ["PLSI", "KIAF"],
}


def _org_kr(name):
    return ORG_ALIAS_KR.get(name, name)


def _wos_is_article(r):
    dt = r.get("DT", "")
    return "Early Access" not in dt


def classify_infra(keywords_list):
    """Classify a paper's KISTI infrastructure from its keyword list."""
    kws = " ".join(keywords_list).upper()
    for infra, patterns in INFRA_KEYWORDS.items():
        for p in patterns:
            if p in kws:
                return infra
    return "기타 KISTI 지원"


# ═══════════════════════════════════════════════════════════
# 1. 데이터 로딩
# ═══════════════════════════════════════════════════════════
def load_data(config: RunConfig):
    print("=== 데이터 로딩 ===")
    print(f"  버전: {config.data_version}, 기간: {config.period_str}"
          + (f", 스냅샷: {config.snapshot}" if config.snapshot else ""))
    wos_data = pickle.load(open(resolve_file("wos_data.pkl", config), "rb"))
    inst_data = pickle.load(open(resolve_file("wos_institutions.pkl", config), "rb"))
    jcr_data = pickle.load(open(resolve_file("jcr_jif.pkl", config), "rb"))
    print(f"  wos_data: {len(wos_data):,}건")
    print(f"  inst_data: {len(inst_data):,}건")

    # ESI 재매핑
    esi_map = pickle.load(open(resolve_file("esi_journal_map.pkl", config), "rb"))
    ESI_TO_INTERNAL = {
        "Environment/Ecology": "Environment Ecology",
        "Psychiatry/Psychology": "Psychiatry Psychology",
    }
    remapped = 0
    for r in wos_data:
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        esi = None
        if sn and sn in esi_map:
            esi = esi_map[sn]
        elif ei and ei in esi_map:
            esi = esi_map[ei]
        if esi:
            r["std_field"] = ESI_TO_INTERNAL.get(esi, esi)
            remapped += 1
        else:
            r["std_field"] = None
    print(f"  ESI 재매핑: {remapped:,}건")

    # Multidisciplinary 재분류
    try:
        multi_path = resolve_file("multi_reclass.pkl", config)
    except FileNotFoundError:
        multi_path = None
    if multi_path and multi_path.exists():
        multi_reclass = pickle.load(open(multi_path, "rb"))
        for r in wos_data:
            if r.get("std_field") == "Multidisciplinary" and r.get("UT") in multi_reclass:
                r["std_field"] = multi_reclass[r["UT"]]

    # institution_type_7 재분류
    reclass_cnt = 0
    for rec in inst_data:
        if rec.get("institution_type_7") != "정부부처":
            continue
        if rec.get("institution_type", rec.get("description", "")) == "기타":
            rec["institution_type_7"] = "국공립연구소"
            reclass_cnt += 1
        elif rec.get("org_alias", "") in _GOVT_TO_NATL_RESEARCH:
            rec["institution_type_7"] = "국공립연구소"
            reclass_cnt += 1
    print(f"  기관유형 재분류: {reclass_cnt:,}건")

    # 유발논문 로딩
    induced_path = resolve_file("kisti_induced_papers.json", config)
    induced_papers = json.loads(induced_path.read_text(encoding="utf-8"))
    print(f"  KISTI 유발논문 JSON: {len(induced_papers):,}건")

    # KBSI 유발논문 로딩
    kbsi_induced_path = resolve_file("kbsi_induced_papers.json", config)
    kbsi_induced_papers = json.loads(kbsi_induced_path.read_text(encoding="utf-8"))
    print(f"  KBSI 유발논문 JSON: {len(kbsi_induced_papers):,}건")

    # IBS 유발논문 로딩
    ibs_induced_path = resolve_file("ibs_induced_papers.json", config)
    ibs_induced_papers = json.loads(ibs_induced_path.read_text(encoding="utf-8"))
    print(f"  IBS 유발논문 JSON: {len(ibs_induced_papers):,}건")

    # PAL 유발논문 로딩
    pal_induced_path = resolve_file("pal_induced_papers.json", config)
    pal_induced_papers = json.loads(pal_induced_path.read_text(encoding="utf-8"))
    print(f"  PAL 유발논문 JSON: {len(pal_induced_papers):,}건")

    # 출연연 학위별 인력 CSV 로딩
    gri_csv_path = Path(__file__).parent / "rawdata" / "국가과학기술연구회 소관 출연연 학위별 인력 정보(정규인력 전체)_20211231.csv"
    gri_personnel = {}
    if gri_csv_path.exists():
        with open(gri_csv_path, "r", encoding="cp949") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["기관명"].strip()
                gri_personnel[name] = {
                    "phd": int(row["박사"]),
                    "master": int(row["석사(박사수료 포함)"]),
                    "bachelor": int(row["학사이하"]),
                    "total": int(row["총현원"]),
                }
        print(f"  출연연 인력 CSV: {len(gri_personnel)}개 기관")
    else:
        print(f"  ⚠ 출연연 인력 CSV 없음: {gri_csv_path}")

    return wos_data, inst_data, jcr_data, induced_papers, kbsi_induced_papers, ibs_induced_papers, pal_induced_papers, gri_personnel


# ═══════════════════════════════════════════════════════════
# 2. 논문 그룹 분류
# ═══════════════════════════════════════════════════════════
def classify_papers(wos_data, inst_data, induced_papers, kbsi_induced_papers, ibs_induced_papers, pal_induced_papers):
    print("\n=== 논문 분류 ===")

    # wos_data를 UT→record 딕셔너리로
    wos_by_ut = {r["UT"]: r for r in wos_data if "UT" in r}

    # inst_data에서 KISTI/KBSI/IBS 소속 UT 추출
    kisti_uts = set()
    kbsi_uts = set()
    ibs_uts = set()
    for rec in inst_data:
        oa = rec.get("org_alias", "")
        ut = rec.get("UT", "")
        if not ut:
            continue
        if oa == KISTI_ORG_ALIAS:
            kisti_uts.add(ut)
        elif oa == KBSI_ORG_ALIAS:
            kbsi_uts.add(ut)
        elif oa == IBS_ORG_ALIAS:
            ibs_uts.add(ut)
    print(f"  KISTI 소속 UT (inst_data): {len(kisti_uts):,}건")
    print(f"  KBSI 소속 UT (inst_data): {len(kbsi_uts):,}건")
    print(f"  IBS 소속 UT (inst_data): {len(ibs_uts):,}건")

    # Article 필터 적용
    kisti_author_uts = {ut for ut in kisti_uts if ut in wos_by_ut and _wos_is_article(wos_by_ut[ut])}
    kbsi_author_uts = {ut for ut in kbsi_uts if ut in wos_by_ut and _wos_is_article(wos_by_ut[ut])}
    ibs_author_uts = {ut for ut in ibs_uts if ut in wos_by_ut and _wos_is_article(wos_by_ut[ut])}
    print(f"  KISTI 소속 UT (Article 필터 후): {len(kisti_author_uts):,}건")
    print(f"  KBSI 소속 UT (Article 필터 후): {len(kbsi_author_uts):,}건")
    print(f"  IBS 소속 UT (Article 필터 후): {len(ibs_author_uts):,}건")

    # ── KISTI 유발논문 ──
    induced_json_uts = set()
    induced_meta = {}
    for p in induced_papers:
        ut = p.get("UT", "")
        if ut:
            induced_json_uts.add(ut)
            induced_meta[ut] = p

    overlap = kisti_author_uts & induced_json_uts
    # 사사표기(FU/FX)가 있으면 소속 저자가 있어도 유발논문으로 분류
    kisti_author_uts = kisti_author_uts - overlap   # 중복분은 직접논문에서 제외
    pure_induced_uts = induced_json_uts             # 사사표기 논문 전체가 유발논문
    print(f"  KISTI 유발논문 JSON UT: {len(induced_json_uts):,}건")
    print(f"  중복(소속+사사) → 유발논문으로 이동: {len(overlap):,}건")
    print(f"  KISTI 직접논문 (사사 제외): {len(kisti_author_uts):,}건")
    print(f"  KISTI 유발논문: {len(pure_induced_uts):,}건")

    induced_matched = 0
    pure_induced_records = []
    for ut in pure_induced_uts:
        if ut in wos_by_ut:
            rec = dict(wos_by_ut[ut])
            rec["_induced_meta"] = induced_meta[ut]
            if _wos_is_article(rec):
                pure_induced_records.append(rec)
                induced_matched += 1
        else:
            jrec = induced_meta[ut]
            rec = {
                "UT": ut,
                "PY": int(jrec.get("PY", 0)),
                "SO": jrec.get("SO", ""),
                "TC": int(jrec.get("TC", 0)),
                "db": jrec.get("db", ""),
                "WC": jrec.get("WC", ""),
                "DT": "",
                "std_field": None,
                "_induced_meta": jrec,
            }
            pure_induced_records.append(rec)
    print(f"  KISTI wos_data 매칭: {induced_matched:,}건")

    # ── KBSI 유발논문 ──
    kbsi_induced_json_uts = set()
    kbsi_induced_meta = {}
    for p in kbsi_induced_papers:
        ut = p.get("UT", "")
        if ut:
            kbsi_induced_json_uts.add(ut)
            kbsi_induced_meta[ut] = p

    kbsi_overlap = kbsi_author_uts & kbsi_induced_json_uts
    # 사사표기(FU/FX)가 있으면 소속 저자가 있어도 유발논문으로 분류
    kbsi_author_uts = kbsi_author_uts - kbsi_overlap   # 중복분은 직접논문에서 제외
    kbsi_pure_induced_uts = kbsi_induced_json_uts       # 사사표기 논문 전체가 유발논문
    print(f"  KBSI 유발논문 JSON UT: {len(kbsi_induced_json_uts):,}건")
    print(f"  중복(소속+사사) → 유발논문으로 이동: {len(kbsi_overlap):,}건")
    print(f"  KBSI 직접논문 (사사 제외): {len(kbsi_author_uts):,}건")
    print(f"  KBSI 유발논문: {len(kbsi_pure_induced_uts):,}건")

    kbsi_induced_matched = 0
    kbsi_pure_induced_records = []
    for ut in kbsi_pure_induced_uts:
        if ut in wos_by_ut:
            rec = dict(wos_by_ut[ut])
            rec["_induced_meta"] = kbsi_induced_meta[ut]
            if _wos_is_article(rec):
                kbsi_pure_induced_records.append(rec)
                kbsi_induced_matched += 1
        else:
            jrec = kbsi_induced_meta[ut]
            rec = {
                "UT": ut,
                "PY": int(jrec.get("PY", 0)),
                "SO": jrec.get("SO", ""),
                "TC": int(jrec.get("TC", 0)),
                "db": jrec.get("db", ""),
                "WC": jrec.get("WC", ""),
                "DT": "",
                "std_field": None,
                "_induced_meta": jrec,
            }
            kbsi_pure_induced_records.append(rec)
    print(f"  KBSI wos_data 매칭: {kbsi_induced_matched:,}건")

    # ── IBS 유발논문 ──
    ibs_induced_json_uts = set()
    ibs_induced_meta = {}
    for p in ibs_induced_papers:
        ut = p.get("UT", "")
        if ut:
            ibs_induced_json_uts.add(ut)
            ibs_induced_meta[ut] = p

    ibs_overlap = ibs_author_uts & ibs_induced_json_uts
    ibs_author_uts = ibs_author_uts - ibs_overlap
    ibs_pure_induced_uts = ibs_induced_json_uts
    print(f"  IBS 유발논문 JSON UT: {len(ibs_induced_json_uts):,}건")
    print(f"  중복(소속+사사) → 유발논문으로 이동: {len(ibs_overlap):,}건")
    print(f"  IBS 직접논문 (사사 제외): {len(ibs_author_uts):,}건")
    print(f"  IBS 유발논문: {len(ibs_pure_induced_uts):,}건")

    ibs_induced_matched = 0
    ibs_pure_induced_records = []
    for ut in ibs_pure_induced_uts:
        if ut in wos_by_ut:
            rec = dict(wos_by_ut[ut])
            rec["_induced_meta"] = ibs_induced_meta[ut]
            if _wos_is_article(rec):
                ibs_pure_induced_records.append(rec)
                ibs_induced_matched += 1
        else:
            jrec = ibs_induced_meta[ut]
            rec = {
                "UT": ut,
                "PY": int(jrec.get("PY", 0)),
                "SO": jrec.get("SO", ""),
                "TC": int(jrec.get("TC", 0)),
                "db": jrec.get("db", ""),
                "WC": jrec.get("WC", ""),
                "DT": "",
                "std_field": None,
                "_induced_meta": jrec,
            }
            ibs_pure_induced_records.append(rec)
    print(f"  IBS wos_data 매칭: {ibs_induced_matched:,}건")

    # ── PAL 유발논문 (직접논문 없음, 유발논문만) ──
    pal_induced_json_uts = set()
    pal_induced_meta = {}
    for p in pal_induced_papers:
        ut = p.get("UT", "")
        if ut:
            pal_induced_json_uts.add(ut)
            pal_induced_meta[ut] = p
    pal_pure_induced_uts = pal_induced_json_uts
    print(f"  PAL 유발논문 JSON UT: {len(pal_induced_json_uts):,}건")

    pal_induced_matched = 0
    pal_pure_induced_records = []
    for ut in pal_pure_induced_uts:
        if ut in wos_by_ut:
            rec = dict(wos_by_ut[ut])
            rec["_induced_meta"] = pal_induced_meta[ut]
            if _wos_is_article(rec):
                pal_pure_induced_records.append(rec)
                pal_induced_matched += 1
        else:
            jrec = pal_induced_meta[ut]
            rec = {
                "UT": ut,
                "PY": int(jrec.get("PY", 0)),
                "SO": jrec.get("SO", ""),
                "TC": int(jrec.get("TC", 0)),
                "db": jrec.get("db", ""),
                "WC": jrec.get("WC", ""),
                "DT": "",
                "std_field": None,
                "_induced_meta": jrec,
            }
            pal_pure_induced_records.append(rec)
    print(f"  PAL wos_data 매칭: {pal_induced_matched:,}건")

    # 논문 레코드
    kisti_records = [wos_by_ut[ut] for ut in kisti_author_uts if ut in wos_by_ut]
    kbsi_records = [wos_by_ut[ut] for ut in kbsi_author_uts if ut in wos_by_ut]
    ibs_records = [wos_by_ut[ut] for ut in ibs_author_uts if ut in wos_by_ut]

    return (wos_by_ut, kisti_records, pure_induced_records, induced_meta,
            kisti_author_uts, pure_induced_uts,
            kbsi_records, kbsi_pure_induced_records, kbsi_induced_meta,
            kbsi_author_uts, kbsi_pure_induced_uts,
            ibs_records, ibs_pure_induced_records, ibs_induced_meta,
            ibs_author_uts, ibs_pure_induced_uts,
            pal_pure_induced_records, pal_induced_meta, pal_pure_induced_uts)


# ═══════════════════════════════════════════════════════════
# 3. 한국 전체 통계 (비교 기준)
# ═══════════════════════════════════════════════════════════
def compute_korea_stats(wos_data, config: RunConfig):
    """한국 전체 논문 연도별/분야별 통계"""
    print("\n=== 한국 전체 통계 ===")
    kr_by_year = defaultdict(int)
    kr_tc_by_year = defaultdict(float)
    kr_by_field = defaultdict(int)
    kr_tc_list_by_year = defaultdict(list)
    kr_tc_by_year_field = defaultdict(lambda: defaultdict(list))  # year → field → [tc...]
    kr_count = 0

    for r in wos_data:
        if not _wos_is_article(r):
            continue
        py = r.get("PY", 0)
        if not isinstance(py, int) or py < config.start_year or py > config.end_year:
            continue
        tc = r.get("TC", 0)
        kr_by_year[py] += 1
        kr_tc_by_year[py] += tc
        kr_tc_list_by_year[py].append(tc)
        kr_count += 1
        f = r.get("std_field")
        if f:
            kr_by_field[f] += 1
            kr_tc_by_year_field[py][f].append(tc)

    # 연도별 상위 10% TC 임계값
    kr_top10p_by_year = {}
    for y, tcs in kr_tc_list_by_year.items():
        sorted_tcs = sorted(tcs, reverse=True)
        idx = max(1, int(len(sorted_tcs) * 0.10))
        kr_top10p_by_year[y] = sorted_tcs[idx - 1] if sorted_tcs else 0

    # 연도×분야별 상위 10% TC 임계값
    kr_top10p_by_year_field = {}
    for y, fields in kr_tc_by_year_field.items():
        kr_top10p_by_year_field[y] = {}
        for f, tcs in fields.items():
            sorted_tcs = sorted(tcs, reverse=True)
            idx = max(1, int(len(sorted_tcs) * 0.10))
            kr_top10p_by_year_field[y][f] = sorted_tcs[idx - 1] if sorted_tcs else 0

    # 연도×분야별 평균 TC (MNCS 계산용)
    kr_avg_tc_by_year_field = {}
    for y, fields in kr_tc_by_year_field.items():
        kr_avg_tc_by_year_field[y] = {}
        for f, tcs in fields.items():
            kr_avg_tc_by_year_field[y][f] = sum(tcs) / len(tcs) if tcs else 0

    print(f"  한국 전체 논문 수: {kr_count:,}")
    print(f"  상위 10% TC 임계값({config.end_year}): {kr_top10p_by_year.get(config.end_year, 'N/A')}")
    return (dict(kr_by_year), dict(kr_tc_by_year), dict(kr_by_field),
            kr_count, kr_top10p_by_year, kr_top10p_by_year_field,
            kr_avg_tc_by_year_field)


# ═══════════════════════════════════════════════════════════
# 섹션 1: KISTI 논문분석
# ═══════════════════════════════════════════════════════════
def compute_sec1(kisti_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, jcr_data, wos_by_ut, kisti_author_uts, config: RunConfig):
    print("\n=== 섹션 1: KISTI 논문분석 ===")
    result = {}
    years = config.years

    # ── 1-1: 발표 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in kisti_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        prev = by_year.get(y - 1, 0)
        growth = round((cnt - prev) / prev * 100, 1) if prev > 0 else 0
        year_data.append({
            "year": y, "count": cnt,
            "growth_rate": growth,
            "kr_share": round(cnt / kr * 100, 2) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec1_1"] = {
        "years": year_data,
        "total": sum(by_year.values()),
    }
    print(f"  1-1 발표현황: {sum(by_year.values()):,}건")

    # ── 1-2: 분야별 현황 ──
    by_field = Counter()
    for r in kisti_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1
    field_data = []
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        # RCA = (KISTI field share) / (Korea field share)
        kisti_total = sum(by_field.values()) or 1
        kr_total = sum(kr_by_field.values()) or 1
        kisti_share = cnt / kisti_total
        kr_share = kr_cnt / kr_total
        rca = round(kisti_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({
            "field": f, "count": cnt, "rca": rca,
            "kisti_share": round(kisti_share * 100, 1),
        })
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec1_2"] = {"fields": field_data}
    print(f"  1-2 분야별: {len(field_data)}개 분야")

    # ── 1-3: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in kisti_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        # HCP: top 1% by TC within year
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs),
            "hcp_count": hcp_count,
        })

    # TC distribution
    all_tcs = [r.get("TC", 0) for r in kisti_records]
    tc_bins = [0, 1, 5, 10, 20, 50, 100, 200, 500]
    tc_dist = []
    for i in range(len(tc_bins)):
        lo = tc_bins[i]
        hi = tc_bins[i + 1] if i + 1 < len(tc_bins) else float("inf")
        label = f"{lo}-{hi-1}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for t in all_tcs if lo <= t < hi)
        tc_dist.append({"label": label, "count": cnt})

    result["sec1_3"] = {"years": impact_data, "tc_distribution": tc_dist}
    print(f"  1-3 영향력: 평균TC={round(sum(all_tcs)/max(len(all_tcs),1), 1)}")

    # ── 1-4: 협력 분석 ──
    collab_counter = Counter()
    for r in kisti_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    # 협력기관 Top20
    kisti_collab_orgs = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in kisti_author_uts and rec.get("org_alias") != KISTI_ORG_ALIAS:
            oa = rec.get("org_alias", "")
            if oa:
                kisti_collab_orgs[oa] += 1
    top_collab = [{"org": _org_kr(o), "org_en": o, "count": c}
                  for o, c in kisti_collab_orgs.most_common(20)]

    # 협력국 Top15 (C1에서 country 파싱)
    # 3글자 이하 제외: 저자 이니셜("S", "T" 등)이 국가로 오파싱되는 것 방지
    country_counter = Counter()
    for r in kisti_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec1_4"] = {
        "collab_types": dict(collab_counter),
        "top_collab_orgs": top_collab,
        "top_countries": top_countries,
    }
    print(f"  1-4 협력: {dict(collab_counter)}")

    # ── 1-5: 학술지 분석 ──
    journal_counter = Counter()
    for r in kisti_records:
        so = r.get("SO", "")
        if so:
            journal_counter[so] += 1
    top_journals = [{"journal": j, "count": c} for j, c in journal_counter.most_common(30)]

    # JIF 분포
    jif_values = []
    for r in kisti_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry and entry.get("jif"):
            try:
                jif_values.append(float(entry["jif"]))
            except (ValueError, TypeError):
                pass

    jif_bins = [0, 1, 2, 3, 5, 10, 20, 50]
    jif_dist = []
    for i in range(len(jif_bins)):
        lo = jif_bins[i]
        hi = jif_bins[i + 1] if i + 1 < len(jif_bins) else float("inf")
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for v in jif_values if lo <= v < hi)
        jif_dist.append({"label": label, "count": cnt})

    # Q1 비율 연도별
    q1_by_year = defaultdict(lambda: {"q1": 0, "total": 0})
    for r in kisti_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry:
            q1_by_year[py]["total"] += 1
            q = entry.get("quartile", "")
            if isinstance(q, str) and q.startswith("Q1"):
                q1_by_year[py]["q1"] += 1

    q1_trend = []
    for y in years:
        d = q1_by_year.get(y, {"q1": 0, "total": 0})
        ratio = round(d["q1"] / d["total"] * 100, 1) if d["total"] > 0 else 0
        q1_trend.append({"year": y, "q1_ratio": ratio, "q1_count": d["q1"], "total": d["total"]})

    result["sec1_5"] = {
        "top_journals": top_journals,
        "jif_distribution": jif_dist,
        "avg_jif": round(sum(jif_values) / max(len(jif_values), 1), 2),
        "q1_trend": q1_trend,
    }
    print(f"  1-5 학술지: Top1={top_journals[0]['journal'] if top_journals else 'N/A'}, 평균JIF={result['sec1_5']['avg_jif']}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 2: KISTI 유발논문분석
# ═══════════════════════════════════════════════════════════
def compute_sec2(pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, induced_meta, pure_induced_uts,
                 kr_avg_tc_by_year_field=None, config: RunConfig = None):
    print("\n=== 섹션 2: KISTI 유발논문분석 ===")
    result = {}
    years = config.years

    # ── 2-1: 유발논문 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        year_data.append({
            "year": y, "count": cnt,
            "kr_share": round(cnt / kr * 100, 3) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec2_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  2-1 현황: {sum(by_year.values()):,}건")

    # ── 2-2: 인프라별 분석 ──
    infra_by_year = defaultdict(lambda: Counter())
    infra_total = Counter()
    for r in pure_induced_records:
        meta = r.get("_induced_meta", {})
        kws = meta.get("keywords", [])
        infra = classify_infra(kws)
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            infra_by_year[py][infra] += 1
        infra_total[infra] += 1

    infra_categories = sorted(infra_total.keys(), key=lambda x: infra_total[x], reverse=True)
    infra_year_data = []
    for y in years:
        row = {"year": y}
        for cat in infra_categories:
            row[cat] = infra_by_year[y].get(cat, 0)
        infra_year_data.append(row)

    result["sec2_2"] = {
        "infra_by_year": infra_year_data,
        "infra_total": dict(infra_total),
        "categories": infra_categories,
    }
    print(f"  2-2 인프라별: {dict(infra_total)}")

    # ── 2-3: 수혜기관 분석 ──
    induced_org_counter = Counter()
    induced_org_type_counter = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in pure_induced_uts:
            oa = rec.get("org_alias", "")
            if oa:
                induced_org_counter[oa] += 1
            itype = rec.get("institution_type_7", "기타")
            if itype:
                induced_org_type_counter[itype] += 1

    top_orgs = [{"org": _org_kr(o), "org_en": o, "count": c}
                for o, c in induced_org_counter.most_common(30)]

    # 기관유형별 (unique UT 기준)
    org_type_by_ut = defaultdict(set)
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in pure_induced_uts:
            itype = rec.get("institution_type_7", "기타")
            org_type_by_ut[itype].add(ut)
    org_type_papers = {k: len(v) for k, v in org_type_by_ut.items()}

    result["sec2_3"] = {
        "top_orgs": top_orgs,
        "org_type_papers": org_type_papers,
    }
    print(f"  2-3 수혜기관: Top1={top_orgs[0]['org'] if top_orgs else 'N/A'}")

    # ── 2-4: 분야별 분석 ──
    by_field = Counter()
    for r in pure_induced_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1

    field_data = []
    ind_total = sum(by_field.values()) or 1
    kr_total = sum(kr_by_field.values()) or 1
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        ind_share = cnt / ind_total
        kr_share = kr_cnt / kr_total
        rca = round(ind_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({"field": f, "count": cnt, "rca": rca})
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec2_4"] = {"fields": field_data}
    print(f"  2-4 분야별: {len([f for f in field_data if f['count'] > 0])}개 활성 분야")

    # ── 2-5: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs), "hcp_count": hcp_count,
        })
    result["sec2_5"] = {"years": impact_data}
    print(f"  2-5 영향력")

    # ── 2-6: 협력 네트워크 ──
    collab_counter = Counter()
    for r in pure_induced_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    country_counter = Counter()
    for r in pure_induced_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec2_6"] = {
        "collab_types": dict(collab_counter),
        "top_countries": top_countries,
    }
    print(f"  2-6 협력: {dict(collab_counter)}")

    # ── 2-7: 경제적 가치 추정 ──
    total_induced = len(pure_induced_records)
    total_tc_induced = sum(r.get("TC", 0) for r in pure_induced_records)
    avg_tc_induced = round(total_tc_induced / max(total_induced, 1), 2)

    # 참고 수치 (출처: KISTEP 국가연구개발사업 성과분석 2022, KREONET 경제적 효과분석)
    cost_per_paper_academic = 1.3   # 억원 — 학술연구 논문 1편당 (교육부 학술연구지원)
    cost_per_paper_gri = 5.0        # 억원 — 출연연 직접연구비 기준 추정
    kreonet_annual_budget = 81      # 억원/년 (2020-2023 평균)
    ksc_annual_budget = 300         # 억원/년 추정 (6호기 총사업비 4,483억 ÷ 15년 운영)
    kisti_infra_annual = kreonet_annual_budget + ksc_annual_budget  # ~381억원/년

    # 유발논문의 연구비 대체가치 (이 논문들을 KISTI 인프라 없이 생산하려면 필요한 연구비)
    value_low = round(total_induced * cost_per_paper_academic, 1)   # 억원
    value_high = round(total_induced * cost_per_paper_gri, 1)       # 억원

    # 연평균 유발논문
    annual_induced = round(total_induced / config.num_years, 1)
    annual_value_low = round(annual_induced * cost_per_paper_academic, 1)
    annual_value_high = round(annual_induced * cost_per_paper_gri, 1)

    # ROI (연간 기준): 연간 유발논문 가치 / 연간 인프라 예산
    roi_low = round(annual_value_low / kisti_infra_annual, 2)
    roi_high = round(annual_value_high / kisti_infra_annual, 2)

    # MNCS (Mean Normalized Citation Score) 계산
    # 각 논문의 TC를 동일 분야·연도 한국 평균 TC로 나눈 값의 평균
    ncs_list = []
    ncs_by_year = defaultdict(list)
    if kr_avg_tc_by_year_field:
        for r in pure_induced_records:
            py = r.get("PY", 0)
            f = r.get("std_field")
            tc = r.get("TC", 0)
            if py in kr_avg_tc_by_year_field and f in kr_avg_tc_by_year_field.get(py, {}):
                expected = kr_avg_tc_by_year_field[py][f]
                if expected > 0:
                    ncs = tc / expected
                    ncs_list.append(ncs)
                    ncs_by_year[py].append(ncs)

    mncs = round(sum(ncs_list) / max(len(ncs_list), 1), 3) if ncs_list else None
    mncs_matched = len(ncs_list)
    # MNCS > 1: 동일 분야·연도 한국 평균보다 높은 영향력
    # 연도별 MNCS 추이
    mncs_trend = {}
    for y in sorted(ncs_by_year.keys()):
        vals = ncs_by_year[y]
        mncs_trend[str(y)] = round(sum(vals) / len(vals), 3) if vals else None

    # 예산 정규화 지표 (연간 기준, 10억원 단위)
    kisti_annual_10b = kisti_infra_annual / 10  # 억원 → 10억원
    papers_per_10b = round(annual_induced / kisti_annual_10b, 2)
    annual_tc = round(total_tc_induced / config.num_years, 1)
    citations_per_10b = round(annual_tc / kisti_annual_10b, 2)

    result["sec2_7"] = {
        "induced_papers": total_induced,
        "total_tc": total_tc_induced,
        "avg_tc": avg_tc_induced,
        "reference": {
            "cost_per_paper_academic": cost_per_paper_academic,
            "cost_per_paper_gri": cost_per_paper_gri,
            "kreonet_annual_budget": kreonet_annual_budget,
            "ksc_annual_budget": ksc_annual_budget,
            "kisti_infra_annual": kisti_infra_annual,
            "kreonet_bc_ratio": [13, 21],
        },
        "value_total_low": value_low,
        "value_total_high": value_high,
        "annual_induced": annual_induced,
        "annual_value_low": annual_value_low,
        "annual_value_high": annual_value_high,
        "roi_low": roi_low,
        "roi_high": roi_high,
        "mncs": mncs,
        "mncs_matched": mncs_matched,
        "mncs_trend": mncs_trend,
        "budget_normalized": {
            "kisti_annual_10b": kisti_annual_10b,
            "papers_per_10b_yr": papers_per_10b,
            "citations_per_10b_yr": citations_per_10b,
            "annual_tc": annual_tc,
        },
    }
    print(f"  2-7 경제적 가치: 유발 {total_induced}편, 대체가치 {value_low}~{value_high}억원, ROI {roi_low}~{roi_high}")
    print(f"      MNCS={mncs} (매칭 {mncs_matched}편), 논문/10억원/년={papers_per_10b}, 피인용/10억원/년={citations_per_10b}")

    # ── 2-8: 국제 비교 ──
    # 출처: Stewart et al. 2023 (Scientometrics), HPCwire 2022, PRACE/EuroHPC 보고서,
    #        NERSC 공식통계, Story of HECToR, Wang & von Laszewski 2021 (PEARC)
    intl = {
        "programs": [
            {
                "name": "KISTI",
                "country": "한국",
                "period": config.period_str,
                "start_year": config.start_year,
                "end_year": config.end_year,
                "type": "슈퍼컴(KSC/NURION) + 연구망(KREONET) + e-Science(EDISON)",
                "papers": total_induced,
                "citations": total_tc_induced,
                "avg_tc": avg_tc_induced,
                "annual_budget_krw": kisti_infra_annual,
                "annual_budget_10b": kisti_infra_annual / 10,
                "users": 3000,
                "top1_pct": None,
                "top5_pct": None,
                "roi": [roi_low, roi_high],
                "note": "유발논문 기준. 직접논문 별도",
                "years_active": config.num_years,
                "mncs": mncs,
            },
            {
                "name": "XSEDE",
                "country": "미국",
                "period": "2011-2022",
                "start_year": 2011,
                "end_year": 2022,
                "type": "NSF 통합 슈퍼컴퓨팅 (15개 시스템, 28.6 PFLOPS)",
                "papers": 20000,
                "citations": 730000,
                "avg_tc": 37,
                "annual_budget_krw": 315,
                "annual_budget_10b": 31.5,
                "users": 17500,
                "top1_pct": 4.8,
                "top5_pct": 22.5,
                "roi": [1.87, 3.24],
                "note": "Stewart et al. 2023 (Scientometrics)",
                "years_active": 11,
                "mncs": None,
            },
            {
                "name": "PRACE",
                "country": "EU 26개국",
                "period": "2010-2023",
                "start_year": 2010,
                "end_year": 2023,
                "type": "유럽 통합 HPC (Tier-0, 7개 시스템)",
                "papers": None,
                "citations": None,
                "avg_tc": None,
                "annual_budget_krw": 230,
                "annual_budget_10b": 23.0,
                "users": 23000,
                "top1_pct": None,
                "top5_pct": None,
                "roi": None,
                "note": "873 프로젝트, 300억 코어시간 배분. 논문 집계 미공개",
                "years_active": 13,
                "mncs": None,
            },
            {
                "name": "NERSC",
                "country": "미국",
                "period": "상시 운영",
                "start_year": None,
                "end_year": None,
                "type": "DOE 과학연구용 슈퍼컴 (Perlmutter 등)",
                "papers": 16000,
                "citations": None,
                "avg_tc": None,
                "annual_budget_krw": None,
                "annual_budget_10b": None,
                "users": 10000,
                "top1_pct": None,
                "top5_pct": None,
                "roi": None,
                "note": "연 ~2,000편 출판. Cori 단일 시스템 10,000+편",
                "years_active": 8,
                "mncs": None,
            },
            {
                "name": "HECToR/ARCHER",
                "country": "영국",
                "period": "2008-2014",
                "start_year": 2008,
                "end_year": 2014,
                "type": "UKRI 국가 슈퍼컴 (HECToR → ARCHER → ARCHER2)",
                "papers": 800,
                "citations": None,
                "avg_tc": None,
                "annual_budget_krw": None,
                "annual_budget_10b": None,
                "users": 2500,
                "top1_pct": None,
                "top5_pct": None,
                "roi": None,
                "note": "HECToR 기간(2008-2014) 800편. 상위 5% 논문 비중 영국 평균 2배",
                "years_active": 6,
                "mncs": None,
            },
        ],
        "sources": [
            "Stewart et al. (2023) Scientometrics 128, 1769-1798",
            "Wang & von Laszewski (2021) PEARC '21, ACM",
            "Knepper et al. (2016) PLOS ONE, PMC4911122",
            "KREONET 경제적 효과분석 (2020-2023), ScienceON",
            "KISTEP 국가연구개발사업 성과분석 보고서 (2022)",
            "HPCwire: A Farewell to XSEDE (2022.7)",
            "Story of HECToR (archer.ac.uk)",
        ],
    }

    # ── 기간 매칭 비교 (Overlap Period Comparison) ──
    # 각 해외 프로그램의 운영기간과 겹치는 기간만 추출하여 KISTI 지표 재계산
    overlap_comparisons = []
    for prog in intl["programs"]:
        if prog["name"] == "KISTI":
            continue
        sy = prog.get("start_year")
        ey = prog.get("end_year")
        if sy is None or ey is None:
            continue  # 기간 미상 프로그램은 스킵
        # 겹치는 기간 계산
        overlap_start = max(sy, config.start_year)
        overlap_end = min(ey, config.end_year)
        if overlap_start > overlap_end:
            continue
        overlap_years = overlap_end - overlap_start + 1

        # KISTI 유발논문 — 겹치는 기간만 필터링
        overlap_records = [r for r in pure_induced_records
                          if overlap_start <= r.get("PY", 0) <= overlap_end]
        k_papers = len(overlap_records)
        k_tc = sum(r.get("TC", 0) for r in overlap_records)
        k_avg_tc = round(k_tc / max(k_papers, 1), 2)

        # 겹치는 기간 MNCS
        k_ncs_list = []
        if kr_avg_tc_by_year_field:
            for r in overlap_records:
                py = r.get("PY", 0)
                f = r.get("std_field")
                tc = r.get("TC", 0)
                if (py in kr_avg_tc_by_year_field
                        and f in kr_avg_tc_by_year_field.get(py, {})):
                    expected = kr_avg_tc_by_year_field[py][f]
                    if expected > 0:
                        k_ncs_list.append(tc / expected)
        k_mncs = round(sum(k_ncs_list) / max(len(k_ncs_list), 1), 3) if k_ncs_list else None

        # 예산 정규화 (KISTI)
        k_budget_10b = kisti_infra_annual / 10
        k_papers_per_yr = round(k_papers / overlap_years, 1)
        k_cites_per_yr = round(k_tc / overlap_years, 1)
        k_papers_per_10b_yr = round(k_papers_per_yr / k_budget_10b, 2) if k_budget_10b else None
        k_cites_per_10b_yr = round(k_cites_per_yr / k_budget_10b, 2) if k_budget_10b else None

        # 예산 정규화 (해외 프로그램)
        p_budget_10b = prog.get("annual_budget_10b")
        p_papers = prog.get("papers")
        p_cites = prog.get("citations")
        p_ya = prog.get("years_active", overlap_years)
        p_papers_per_yr = round(p_papers / p_ya, 1) if p_papers else None
        p_cites_per_yr = round(p_cites / p_ya, 1) if p_cites else None
        p_papers_per_10b_yr = round(p_papers_per_yr / p_budget_10b, 2) if (p_papers_per_yr and p_budget_10b) else None
        p_cites_per_10b_yr = round(p_cites_per_yr / p_budget_10b, 2) if (p_cites_per_yr and p_budget_10b) else None

        # 데이터 경고: 2008-2018 SCIE 원시 데이터 부재로 유발논문 과소 집계 가능 구간
        caveat = None
        if overlap_end <= 2018:
            caveat = "KISTI 유발논문은 2008-2018 SCIE 원시 데이터 부재로 이 기간 집계가 극히 불완전합니다. 비교 참고에만 활용하세요."
        elif overlap_start < 2019 and k_papers < 200:
            caveat = "겹치는 기간 중 초기(~2018)에 SCIE 원시 데이터 부재로 KISTI 유발논문이 과소 집계되었습니다."

        comp = {
            "program": prog["name"],
            "country": prog["country"],
            "overlap_period": f"{overlap_start}-{overlap_end}",
            "overlap_years": overlap_years,
            "caveat": caveat,
            "kisti": {
                "papers": k_papers,
                "citations": k_tc,
                "avg_tc": k_avg_tc,
                "mncs": k_mncs,
                "papers_per_yr": k_papers_per_yr,
                "citations_per_yr": k_cites_per_yr,
                "papers_per_10b_yr": k_papers_per_10b_yr,
                "citations_per_10b_yr": k_cites_per_10b_yr,
            },
            "other": {
                "papers": p_papers,
                "citations": p_cites,
                "avg_tc": prog.get("avg_tc"),
                "roi": prog.get("roi"),
                "papers_per_yr": p_papers_per_yr,
                "citations_per_yr": p_cites_per_yr,
                "papers_per_10b_yr": p_papers_per_10b_yr,
                "citations_per_10b_yr": p_cites_per_10b_yr,
                "top1_pct": prog.get("top1_pct"),
                "top5_pct": prog.get("top5_pct"),
            },
        }
        overlap_comparisons.append(comp)
        print(f"    기간매칭 KISTI vs {prog['name']} ({overlap_start}-{overlap_end}, {overlap_years}년): "
              f"KISTI {k_papers}편 vs {p_papers}편, "
              f"KISTI 논문/10억/yr={k_papers_per_10b_yr} vs {p_papers_per_10b_yr}")

    intl["overlap_comparisons"] = overlap_comparisons

    # 예산 정규화 비교표 계산 (10억원 단위) — 전체 기간 기준 (참고용)
    normalized = []
    for p in intl["programs"]:
        entry = {"name": p["name"]}
        ya = p.get("years_active", 1)
        budget_10b = p.get("annual_budget_10b")
        papers = p.get("papers")
        cites = p.get("citations")

        entry["papers_per_yr"] = round(papers / ya, 1) if papers else None
        entry["citations_per_yr"] = round(cites / ya, 1) if cites else None
        if papers and budget_10b:
            entry["papers_per_10b_yr"] = round((papers / ya) / budget_10b, 2)
        else:
            entry["papers_per_10b_yr"] = None
        if cites and budget_10b:
            entry["citations_per_10b_yr"] = round((cites / ya) / budget_10b, 2)
        else:
            entry["citations_per_10b_yr"] = None
        entry["mncs"] = p.get("mncs")
        normalized.append(entry)

    intl["normalized"] = normalized
    result["sec2_8"] = intl
    print(f"  2-8 국제 비교: {len(intl['programs'])}개 프로그램, 기간매칭 비교 {len(overlap_comparisons)}건")
    for n in normalized:
        print(f"      {n['name']:15s} 논문/yr={n['papers_per_yr']}, 논문/10억/yr={n['papers_per_10b_yr']}, 피인용/10억/yr={n['citations_per_10b_yr']}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 3: 비교·종합
# ═══════════════════════════════════════════════════════════
def compute_sec3(kisti_records, pure_induced_records, kr_by_year, kr_tc_by_year,
                 jcr_data, config: RunConfig):
    print("\n=== 섹션 3: 비교·종합 ===")
    result = {}
    years = config.years

    # ── 3-1: KISTI vs 유발논문 비교 ──
    def _stats(records):
        total = len(records)
        tcs = [r.get("TC", 0) for r in records]
        avg_tc = round(sum(tcs) / max(total, 1), 2)
        # Q1 ratio
        q1, jcr_matched = 0, 0
        for r in records:
            py = r.get("PY", 0)
            if py not in jcr_data:
                continue
            sn = r.get("SN", "").strip()
            ei = r.get("EI", "").strip()
            jcr_yr = jcr_data[py]
            entry = None
            if sn and sn in jcr_yr.get("by_issn", {}):
                entry = jcr_yr["by_issn"][sn]
            elif ei and ei in jcr_yr.get("by_eissn", {}):
                entry = jcr_yr["by_eissn"][ei]
            if entry:
                jcr_matched += 1
                q = entry.get("quartile", "")
                if isinstance(q, str) and q.startswith("Q1"):
                    q1 += 1
        q1_ratio = round(q1 / max(jcr_matched, 1) * 100, 1)
        return {"papers": total, "avg_tc": avg_tc, "total_tc": sum(tcs), "q1_ratio": q1_ratio}

    kisti_stats = _stats(kisti_records)
    induced_stats = _stats(pure_induced_records)
    result["sec3_1"] = {"kisti": kisti_stats, "induced": induced_stats}
    print(f"  3-1 비교: KISTI={kisti_stats['papers']}, 유발={induced_stats['papers']}")

    # ── 3-2: 기여도 종합 ──
    combined_data = []
    for y in years:
        k_cnt = sum(1 for r in kisti_records if r.get("PY") == y)
        i_cnt = sum(1 for r in pure_induced_records
                    if (isinstance(r.get("PY"), int) and r.get("PY") == y))
        total = k_cnt + i_cnt
        kr = kr_by_year.get(y, 1)
        combined_data.append({
            "year": y, "kisti": k_cnt, "induced": i_cnt,
            "total": total,
            "kr_share": round(total / kr * 100, 2) if kr else 0,
        })
    result["sec3_2"] = {"years": combined_data}
    print(f"  3-2 기여도 종합")

    # ── 3-3: 인프라 투자 효과 ──
    infra_year_count = defaultdict(lambda: Counter())
    infra_year_tc = defaultdict(lambda: defaultdict(list))
    for r in pure_induced_records:
        meta = r.get("_induced_meta", {})
        kws = meta.get("keywords", [])
        infra = classify_infra(kws)
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            infra_year_count[infra][py] += 1
            infra_year_tc[infra][py].append(r.get("TC", 0))

    infra_trend = {}
    for infra in infra_year_count:
        trend = []
        for y in years:
            cnt = infra_year_count[infra].get(y, 0)
            tcs = infra_year_tc[infra].get(y, [])
            avg_tc = round(sum(tcs) / max(len(tcs), 1), 2)
            trend.append({"year": y, "count": cnt, "avg_tc": avg_tc})
        infra_trend[infra] = trend

    result["sec3_3"] = {"infra_trends": infra_trend}
    print(f"  3-3 인프라 효과: {list(infra_trend.keys())}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 4: KBSI 논문분석 (sec1과 동일 로직, KBSI 데이터 적용)
# ═══════════════════════════════════════════════════════════
def compute_sec4(kbsi_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, jcr_data, wos_by_ut, kbsi_author_uts, config: RunConfig):
    print("\n=== 섹션 4: KBSI 논문분석 ===")
    result = {}
    years = config.years

    # ── 4-1: 발표 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in kbsi_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        prev = by_year.get(y - 1, 0)
        growth = round((cnt - prev) / prev * 100, 1) if prev > 0 else 0
        year_data.append({
            "year": y, "count": cnt,
            "growth_rate": growth,
            "kr_share": round(cnt / kr * 100, 2) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec4_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  4-1 발표현황: {sum(by_year.values()):,}건")

    # ── 4-2: 분야별 현황 ──
    by_field = Counter()
    for r in kbsi_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1
    field_data = []
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        kbsi_total = sum(by_field.values()) or 1
        kr_total = sum(kr_by_field.values()) or 1
        kbsi_share = cnt / kbsi_total
        kr_share = kr_cnt / kr_total
        rca = round(kbsi_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({
            "field": f, "count": cnt, "rca": rca,
            "kbsi_share": round(kbsi_share * 100, 1),
        })
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec4_2"] = {"fields": field_data}
    print(f"  4-2 분야별: {len(field_data)}개 분야")

    # ── 4-3: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in kbsi_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs),
            "hcp_count": hcp_count,
        })

    all_tcs = [r.get("TC", 0) for r in kbsi_records]
    tc_bins = [0, 1, 5, 10, 20, 50, 100, 200, 500]
    tc_dist = []
    for i in range(len(tc_bins)):
        lo = tc_bins[i]
        hi = tc_bins[i + 1] if i + 1 < len(tc_bins) else float("inf")
        label = f"{lo}-{hi-1}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for t in all_tcs if lo <= t < hi)
        tc_dist.append({"label": label, "count": cnt})

    result["sec4_3"] = {"years": impact_data, "tc_distribution": tc_dist}
    print(f"  4-3 영향력: 평균TC={round(sum(all_tcs)/max(len(all_tcs),1), 1)}")

    # ── 4-4: 협력 분석 ──
    collab_counter = Counter()
    for r in kbsi_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    kbsi_collab_orgs = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in kbsi_author_uts and rec.get("org_alias") != KBSI_ORG_ALIAS:
            oa = rec.get("org_alias", "")
            if oa:
                kbsi_collab_orgs[oa] += 1
    top_collab = [{"org": _org_kr(o), "org_en": o, "count": c}
                  for o, c in kbsi_collab_orgs.most_common(20)]

    country_counter = Counter()
    for r in kbsi_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec4_4"] = {
        "collab_types": dict(collab_counter),
        "top_collab_orgs": top_collab,
        "top_countries": top_countries,
    }
    print(f"  4-4 협력: {dict(collab_counter)}")

    # ── 4-5: 학술지 분석 ──
    journal_counter = Counter()
    for r in kbsi_records:
        so = r.get("SO", "")
        if so:
            journal_counter[so] += 1
    top_journals = [{"journal": j, "count": c} for j, c in journal_counter.most_common(30)]

    jif_values = []
    for r in kbsi_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry and entry.get("jif"):
            try:
                jif_values.append(float(entry["jif"]))
            except (ValueError, TypeError):
                pass

    jif_bins = [0, 1, 2, 3, 5, 10, 20, 50]
    jif_dist = []
    for i in range(len(jif_bins)):
        lo = jif_bins[i]
        hi = jif_bins[i + 1] if i + 1 < len(jif_bins) else float("inf")
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for v in jif_values if lo <= v < hi)
        jif_dist.append({"label": label, "count": cnt})

    q1_by_year = defaultdict(lambda: {"q1": 0, "total": 0})
    for r in kbsi_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry:
            q1_by_year[py]["total"] += 1
            q = entry.get("quartile", "")
            if isinstance(q, str) and q.startswith("Q1"):
                q1_by_year[py]["q1"] += 1

    q1_trend = []
    for y in years:
        d = q1_by_year.get(y, {"q1": 0, "total": 0})
        ratio = round(d["q1"] / d["total"] * 100, 1) if d["total"] > 0 else 0
        q1_trend.append({"year": y, "q1_ratio": ratio, "q1_count": d["q1"], "total": d["total"]})

    result["sec4_5"] = {
        "top_journals": top_journals,
        "jif_distribution": jif_dist,
        "avg_jif": round(sum(jif_values) / max(len(jif_values), 1), 2),
        "q1_trend": q1_trend,
    }
    print(f"  4-5 학술지: Top1={top_journals[0]['journal'] if top_journals else 'N/A'}, 평균JIF={result['sec4_5']['avg_jif']}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 5: KBSI 유발논문분석 (sec2와 동일 로직, KBSI 데이터 적용)
# ═══════════════════════════════════════════════════════════
def compute_sec5(kbsi_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, kbsi_induced_meta, kbsi_pure_induced_uts, config: RunConfig):
    print("\n=== 섹션 5: KBSI 유발논문분석 ===")
    result = {}
    years = config.years

    # ── 5-1: 유발논문 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in kbsi_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        year_data.append({
            "year": y, "count": cnt,
            "kr_share": round(cnt / kr * 100, 3) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec5_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  5-1 현황: {sum(by_year.values()):,}건")

    # ── 5-2: 인프라별 분석 (KBSI: 단일 분류 "KBSI 분석장비 지원") ──
    infra_total = Counter()
    infra_by_year = defaultdict(lambda: Counter())
    for r in kbsi_pure_induced_records:
        infra = "KBSI 분석장비 지원"
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            infra_by_year[py][infra] += 1
        infra_total[infra] += 1

    infra_categories = sorted(infra_total.keys(), key=lambda x: infra_total[x], reverse=True)
    infra_year_data = []
    for y in years:
        row = {"year": y}
        for cat in infra_categories:
            row[cat] = infra_by_year[y].get(cat, 0)
        infra_year_data.append(row)

    result["sec5_2"] = {
        "infra_by_year": infra_year_data,
        "infra_total": dict(infra_total),
        "categories": infra_categories,
    }
    print(f"  5-2 인프라별: {dict(infra_total)}")

    # ── 5-3: 수혜기관 분석 ──
    induced_org_counter = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in kbsi_pure_induced_uts:
            oa = rec.get("org_alias", "")
            if oa:
                induced_org_counter[oa] += 1

    top_orgs = [{"org": _org_kr(o), "org_en": o, "count": c}
                for o, c in induced_org_counter.most_common(30)]

    org_type_by_ut = defaultdict(set)
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in kbsi_pure_induced_uts:
            itype = rec.get("institution_type_7", "기타")
            org_type_by_ut[itype].add(ut)
    org_type_papers = {k: len(v) for k, v in org_type_by_ut.items()}

    result["sec5_3"] = {
        "top_orgs": top_orgs,
        "org_type_papers": org_type_papers,
    }
    print(f"  5-3 수혜기관: Top1={top_orgs[0]['org'] if top_orgs else 'N/A'}")

    # ── 5-4: 분야별 분석 ──
    by_field = Counter()
    for r in kbsi_pure_induced_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1

    field_data = []
    ind_total = sum(by_field.values()) or 1
    kr_total = sum(kr_by_field.values()) or 1
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        ind_share = cnt / ind_total
        kr_share = kr_cnt / kr_total
        rca = round(ind_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({"field": f, "count": cnt, "rca": rca})
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec5_4"] = {"fields": field_data}
    print(f"  5-4 분야별: {len([f for f in field_data if f['count'] > 0])}개 활성 분야")

    # ── 5-5: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in kbsi_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs), "hcp_count": hcp_count,
        })
    result["sec5_5"] = {"years": impact_data}
    print(f"  5-5 영향력")

    # ── 5-6: 협력 네트워크 ──
    collab_counter = Counter()
    for r in kbsi_pure_induced_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    country_counter = Counter()
    for r in kbsi_pure_induced_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec5_6"] = {
        "collab_types": dict(collab_counter),
        "top_countries": top_countries,
    }
    print(f"  5-6 협력: {dict(collab_counter)}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 6: KISTI vs KBSI 비교
# ═══════════════════════════════════════════════════════════
def compute_sec6(kisti_records, pure_induced_records,
                 kbsi_records, kbsi_pure_induced_records,
                 kr_by_year, kr_tc_by_year, jcr_data,
                 gri_personnel=None, kr_top10p_by_year=None,
                 kr_top10p_by_year_field=None, config: RunConfig = None):
    print("\n=== 섹션 6: KISTI vs KBSI 비교 ===")
    result = {}
    years = config.years

    def _stats(records):
        total = len(records)
        tcs = [r.get("TC", 0) for r in records]
        avg_tc = round(sum(tcs) / max(total, 1), 2)
        q1, jcr_matched = 0, 0
        for r in records:
            py = r.get("PY", 0)
            if py not in jcr_data:
                continue
            sn = r.get("SN", "").strip()
            ei = r.get("EI", "").strip()
            jcr_yr = jcr_data[py]
            entry = None
            if sn and sn in jcr_yr.get("by_issn", {}):
                entry = jcr_yr["by_issn"][sn]
            elif ei and ei in jcr_yr.get("by_eissn", {}):
                entry = jcr_yr["by_eissn"][ei]
            if entry:
                jcr_matched += 1
                q = entry.get("quartile", "")
                if isinstance(q, str) and q.startswith("Q1"):
                    q1 += 1
        q1_ratio = round(q1 / max(jcr_matched, 1) * 100, 1)
        return {"papers": total, "avg_tc": avg_tc, "total_tc": sum(tcs), "q1_ratio": q1_ratio}

    # ── 6-1: 직접 논문 비교 ──
    kisti_stats = _stats(kisti_records)
    kbsi_stats = _stats(kbsi_records)
    result["sec6_1"] = {"kisti": kisti_stats, "kbsi": kbsi_stats}
    print(f"  6-1 직접비교: KISTI={kisti_stats['papers']}, KBSI={kbsi_stats['papers']}")

    # ── 6-2: 유발논문 비교 ──
    kisti_ind_stats = _stats(pure_induced_records)
    kbsi_ind_stats = _stats(kbsi_pure_induced_records)
    result["sec6_2"] = {"kisti_induced": kisti_ind_stats, "kbsi_induced": kbsi_ind_stats}
    print(f"  6-2 유발비교: KISTI유발={kisti_ind_stats['papers']}, KBSI유발={kbsi_ind_stats['papers']}")

    # ── 6-3: 4자 종합 비교 + 연도별 추이 ──
    combined_data = []
    for y in years:
        k_cnt = sum(1 for r in kisti_records if r.get("PY") == y)
        ki_cnt = sum(1 for r in pure_induced_records
                     if isinstance(r.get("PY"), int) and r.get("PY") == y)
        b_cnt = sum(1 for r in kbsi_records if r.get("PY") == y)
        bi_cnt = sum(1 for r in kbsi_pure_induced_records
                     if isinstance(r.get("PY"), int) and r.get("PY") == y)
        kr = kr_by_year.get(y, 1)
        combined_data.append({
            "year": y,
            "kisti": k_cnt, "kisti_induced": ki_cnt,
            "kbsi": b_cnt, "kbsi_induced": bi_cnt,
            "kisti_total": k_cnt + ki_cnt,
            "kbsi_total": b_cnt + bi_cnt,
            "kisti_kr_share": round((k_cnt + ki_cnt) / kr * 100, 3) if kr else 0,
            "kbsi_kr_share": round((b_cnt + bi_cnt) / kr * 100, 3) if kr else 0,
        })

    # 연도별 평균TC 추이
    def _year_avg_tc(records):
        tc_by_y = defaultdict(list)
        for r in records:
            py = r.get("PY", 0)
            if isinstance(py, int) and config.start_year <= py <= config.end_year:
                tc_by_y[py].append(r.get("TC", 0))
        return {y: round(sum(tcs)/max(len(tcs),1), 2) for y, tcs in tc_by_y.items()}

    kisti_tc_trend = _year_avg_tc(kisti_records)
    kbsi_tc_trend = _year_avg_tc(kbsi_records)
    kisti_ind_tc_trend = _year_avg_tc(pure_induced_records)
    kbsi_ind_tc_trend = _year_avg_tc(kbsi_pure_induced_records)

    tc_trend_data = []
    for y in years:
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        tc_trend_data.append({
            "year": y,
            "kisti_avg_tc": kisti_tc_trend.get(y, 0),
            "kbsi_avg_tc": kbsi_tc_trend.get(y, 0),
            "kisti_ind_avg_tc": kisti_ind_tc_trend.get(y, 0),
            "kbsi_ind_avg_tc": kbsi_ind_tc_trend.get(y, 0),
            "kr_avg_tc": kr_avg,
        })

    result["sec6_3"] = {
        "years": combined_data,
        "tc_trend": tc_trend_data,
        "summary": {
            "kisti": kisti_stats, "kisti_induced": kisti_ind_stats,
            "kbsi": kbsi_stats, "kbsi_induced": kbsi_ind_stats,
        },
    }
    print(f"  6-3 종합비교")

    # ── 6-4: 출연연 인력 생산성 분석 ──
    if gri_personnel:
        kisti_name = "한국과학기술정보연구원"
        kbsi_name = "한국기초과학지원연구원"
        kisti_pers = gri_personnel.get(kisti_name, {})
        kbsi_pers = gri_personnel.get(kbsi_name, {})

        k_papers = kisti_stats["papers"]
        k_induced = kisti_ind_stats["papers"]
        k_combined = k_papers + k_induced
        k_total = kisti_pers.get("total", 1)
        k_phd = kisti_pers.get("phd", 1)

        b_papers = kbsi_stats["papers"]
        b_induced = kbsi_ind_stats["papers"]
        b_combined = b_papers + b_induced
        b_total = kbsi_pers.get("total", 1)
        b_phd = kbsi_pers.get("phd", 1)

        def _prod(inst_pers, papers, induced):
            total = inst_pers.get("total", 1)
            phd = inst_pers.get("phd", 1)
            combined = papers + induced
            return {
                **inst_pers,
                "papers": papers,
                "induced": induced,
                "combined": combined,
                "papers_per_total": round(papers / max(total, 1), 2),
                "papers_per_phd": round(papers / max(phd, 1), 2),
                "combined_per_total": round(combined / max(total, 1), 2),
                "combined_per_phd": round(combined / max(phd, 1), 2),
            }

        kisti_prod = _prod(kisti_pers, k_papers, k_induced)
        kisti_prod["avg_tc"] = kisti_stats["avg_tc"]
        kisti_prod["total_tc"] = kisti_stats["total_tc"]

        kbsi_prod = _prod(kbsi_pers, b_papers, b_induced)
        kbsi_prod["avg_tc"] = kbsi_stats["avg_tc"]
        kbsi_prod["total_tc"] = kbsi_stats["total_tc"]

        # 유발논문 상위 10% 비중 계산
        def _top10p_ratio(records, thresholds):
            """한국 전체 연도별 상위 10% TC 임계값 대비 해당 논문의 비중"""
            if not thresholds or not records:
                return 0.0, 0, len(records)
            top10_cnt = 0
            for r in records:
                py = r.get("PY", 0)
                tc = r.get("TC", 0)
                thr = thresholds.get(py, float("inf"))
                if tc >= thr and tc > 0:
                    top10_cnt += 1
            total = len(records)
            ratio = round(top10_cnt / max(total, 1) * 100, 1)
            return ratio, top10_cnt, total

        ki_top10p_ratio, ki_top10p_cnt, ki_total_cnt = _top10p_ratio(
            pure_induced_records, kr_top10p_by_year)
        bi_top10p_ratio, bi_top10p_cnt, bi_total_cnt = _top10p_ratio(
            kbsi_pure_induced_records, kr_top10p_by_year)
        # 직접 논문도 계산
        k_top10p_ratio, k_top10p_cnt, _ = _top10p_ratio(
            kisti_records, kr_top10p_by_year)
        b_top10p_ratio, b_top10p_cnt, _ = _top10p_ratio(
            kbsi_records, kr_top10p_by_year)

        kisti_prod["top10p_induced_ratio"] = ki_top10p_ratio
        kisti_prod["top10p_induced_count"] = ki_top10p_cnt
        kisti_prod["top10p_direct_ratio"] = k_top10p_ratio
        kisti_prod["top10p_direct_count"] = k_top10p_cnt
        kbsi_prod["top10p_induced_ratio"] = bi_top10p_ratio
        kbsi_prod["top10p_induced_count"] = bi_top10p_cnt
        kbsi_prod["top10p_direct_ratio"] = b_top10p_ratio
        kbsi_prod["top10p_direct_count"] = b_top10p_cnt

        # 분야별 상위 10% 비중 계산
        def _top10p_field_ratio(records, thresholds_yf):
            """분야별 상위 10% TC 비중: 각 논문을 같은 연도·분야 임계값과 비교"""
            if not thresholds_yf or not records:
                return 0.0, 0, len(records)
            top10_cnt = 0
            valid_cnt = 0  # 분야 정보가 있는 논문만
            for r in records:
                py = r.get("PY", 0)
                f = r.get("std_field")
                if not f:
                    continue
                valid_cnt += 1
                tc = r.get("TC", 0)
                yr_fields = thresholds_yf.get(py, {})
                thr = yr_fields.get(f, float("inf"))
                if tc >= thr and tc > 0:
                    top10_cnt += 1
            ratio = round(top10_cnt / max(valid_cnt, 1) * 100, 1)
            return ratio, top10_cnt, valid_cnt

        ki_ftop10_ratio, ki_ftop10_cnt, ki_ftop10_valid = _top10p_field_ratio(
            pure_induced_records, kr_top10p_by_year_field)
        bi_ftop10_ratio, bi_ftop10_cnt, bi_ftop10_valid = _top10p_field_ratio(
            kbsi_pure_induced_records, kr_top10p_by_year_field)
        k_ftop10_ratio, k_ftop10_cnt, k_ftop10_valid = _top10p_field_ratio(
            kisti_records, kr_top10p_by_year_field)
        b_ftop10_ratio, b_ftop10_cnt, b_ftop10_valid = _top10p_field_ratio(
            kbsi_records, kr_top10p_by_year_field)

        kisti_prod["ftop10p_induced_ratio"] = ki_ftop10_ratio
        kisti_prod["ftop10p_induced_count"] = ki_ftop10_cnt
        kisti_prod["ftop10p_direct_ratio"] = k_ftop10_ratio
        kisti_prod["ftop10p_direct_count"] = k_ftop10_cnt
        kbsi_prod["ftop10p_induced_ratio"] = bi_ftop10_ratio
        kbsi_prod["ftop10p_induced_count"] = bi_ftop10_cnt
        kbsi_prod["ftop10p_direct_ratio"] = b_ftop10_ratio
        kbsi_prod["ftop10p_direct_count"] = b_ftop10_cnt

        # 저널 분위(Q1-Q4) 분포 계산
        def _quartile_dist(records):
            """Q1/Q2/Q3/Q4/미매칭 분포"""
            dist = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0, "미매칭": 0}
            for r in records:
                py = r.get("PY", 0)
                if py not in jcr_data:
                    dist["미매칭"] += 1
                    continue
                sn = r.get("SN", "").strip()
                ei = r.get("EI", "").strip()
                jcr_yr = jcr_data[py]
                entry = None
                if sn and sn in jcr_yr.get("by_issn", {}):
                    entry = jcr_yr["by_issn"][sn]
                elif ei and ei in jcr_yr.get("by_eissn", {}):
                    entry = jcr_yr["by_eissn"][ei]
                if not entry:
                    dist["미매칭"] += 1
                    continue
                q = entry.get("quartile", "")
                if isinstance(q, str) and q.startswith("Q1"):
                    dist["Q1"] += 1
                elif isinstance(q, str) and q.startswith("Q2"):
                    dist["Q2"] += 1
                elif isinstance(q, str) and q.startswith("Q3"):
                    dist["Q3"] += 1
                elif isinstance(q, str) and q.startswith("Q4"):
                    dist["Q4"] += 1
                else:
                    dist["미매칭"] += 1
            total_matched = dist["Q1"] + dist["Q2"] + dist["Q3"] + dist["Q4"]
            for q in ["Q1", "Q2", "Q3", "Q4"]:
                dist[f"{q}_ratio"] = round(dist[q] / max(total_matched, 1) * 100, 1)
            dist["matched"] = total_matched
            return dist

        ki_qdist = _quartile_dist(pure_induced_records)
        bi_qdist = _quartile_dist(kbsi_pure_induced_records)
        k_qdist = _quartile_dist(kisti_records)
        b_qdist = _quartile_dist(kbsi_records)

        kisti_prod["quartile_direct"] = k_qdist
        kisti_prod["quartile_induced"] = ki_qdist
        kbsi_prod["quartile_direct"] = b_qdist
        kbsi_prod["quartile_induced"] = bi_qdist

        # 25개 출연연 목록 (총현원 내림차순)
        all_gri = []
        for name, pers in sorted(gri_personnel.items(),
                                 key=lambda x: x[1]["total"], reverse=True):
            all_gri.append({"name": name, **pers})

        # 비교 테이블
        comparison = {
            "metrics": ["총현원", "박사", "석사", "학사이하",
                        "논문수", "유발논문수", "합산논문수",
                        "1인당 논문(총현원)", "1인당 논문(박사)",
                        "1인당 합산(총현원)", "1인당 합산(박사)",
                        "직접논문 상위10%건수(전체)", "직접논문 상위10%비율(%,전체)",
                        "유발논문 상위10%건수(전체)", "유발논문 상위10%비율(%,전체)",
                        "직접논문 상위10%건수(분야별)", "직접논문 상위10%비율(%,분야별)",
                        "유발논문 상위10%건수(분야별)", "유발논문 상위10%비율(%,분야별)",
                        "직접논문 Q1건수", "직접논문 Q1비율(%)",
                        "유발논문 Q1건수", "유발논문 Q1비율(%)"],
            "kisti": [k_total, kisti_pers.get("phd", 0),
                      kisti_pers.get("master", 0), kisti_pers.get("bachelor", 0),
                      k_papers, k_induced, k_combined,
                      kisti_prod["papers_per_total"], kisti_prod["papers_per_phd"],
                      kisti_prod["combined_per_total"], kisti_prod["combined_per_phd"],
                      k_top10p_cnt, k_top10p_ratio,
                      ki_top10p_cnt, ki_top10p_ratio,
                      k_ftop10_cnt, k_ftop10_ratio,
                      ki_ftop10_cnt, ki_ftop10_ratio,
                      k_qdist["Q1"], k_qdist["Q1_ratio"],
                      ki_qdist["Q1"], ki_qdist["Q1_ratio"]],
            "kbsi": [b_total, kbsi_pers.get("phd", 0),
                     kbsi_pers.get("master", 0), kbsi_pers.get("bachelor", 0),
                     b_papers, b_induced, b_combined,
                     kbsi_prod["papers_per_total"], kbsi_prod["papers_per_phd"],
                     kbsi_prod["combined_per_total"], kbsi_prod["combined_per_phd"],
                     b_top10p_cnt, b_top10p_ratio,
                     bi_top10p_cnt, bi_top10p_ratio,
                     b_ftop10_cnt, b_ftop10_ratio,
                     bi_ftop10_cnt, bi_ftop10_ratio,
                     b_qdist["Q1"], b_qdist["Q1_ratio"],
                     bi_qdist["Q1"], bi_qdist["Q1_ratio"]],
        }

        result["sec6_4"] = {
            "kisti": kisti_prod,
            "kbsi": kbsi_prod,
            "all_gri": all_gri,
            "comparison": comparison,
        }
        print(f"  6-4 인력생산성: KISTI 총현원={k_total}, KBSI 총현원={b_total}")
        print(f"      유발논문 상위10%(전체): KISTI={ki_top10p_cnt}/{ki_total_cnt}({ki_top10p_ratio}%), "
              f"KBSI={bi_top10p_cnt}/{bi_total_cnt}({bi_top10p_ratio}%)")
        print(f"      유발논문 상위10%(분야별): KISTI={ki_ftop10_cnt}/{ki_ftop10_valid}({ki_ftop10_ratio}%), "
              f"KBSI={bi_ftop10_cnt}/{bi_ftop10_valid}({bi_ftop10_ratio}%)")
        print(f"      유발논문 Q1: KISTI={ki_qdist['Q1']}/{ki_qdist['matched']}({ki_qdist['Q1_ratio']}%), "
              f"KBSI={bi_qdist['Q1']}/{bi_qdist['matched']}({bi_qdist['Q1_ratio']}%)")
    else:
        result["sec6_4"] = None
        print(f"  6-4 인력생산성: CSV 데이터 없음 — 건너뜀")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 7: IBS 논문분석 (sec4와 동일 로직, IBS 데이터 적용)
# ═══════════════════════════════════════════════════════════
def compute_sec7(ibs_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, jcr_data, wos_by_ut, ibs_author_uts, config: RunConfig):
    print("\n=== 섹션 7: IBS 논문분석 ===")
    result = {}
    years = config.years

    # ── 7-1: 발표 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in ibs_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        prev = by_year.get(y - 1, 0)
        growth = round((cnt - prev) / prev * 100, 1) if prev > 0 else 0
        year_data.append({
            "year": y, "count": cnt,
            "growth_rate": growth,
            "kr_share": round(cnt / kr * 100, 2) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec7_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  7-1 발표현황: {sum(by_year.values()):,}건")

    # ── 7-2: 분야별 현황 ──
    by_field = Counter()
    for r in ibs_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1
    field_data = []
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        ibs_total = sum(by_field.values()) or 1
        kr_total = sum(kr_by_field.values()) or 1
        ibs_share = cnt / ibs_total
        kr_share = kr_cnt / kr_total
        rca = round(ibs_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({
            "field": f, "count": cnt, "rca": rca,
            "kbsi_share": round(ibs_share * 100, 1),
        })
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec7_2"] = {"fields": field_data}
    print(f"  7-2 분야별: {len(field_data)}개 분야")

    # ── 7-3: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in ibs_records:
        py = r.get("PY", 0)
        if config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs),
            "hcp_count": hcp_count,
        })

    all_tcs = [r.get("TC", 0) for r in ibs_records]
    tc_bins = [0, 1, 5, 10, 20, 50, 100, 200, 500]
    tc_dist = []
    for i in range(len(tc_bins)):
        lo = tc_bins[i]
        hi = tc_bins[i + 1] if i + 1 < len(tc_bins) else float("inf")
        label = f"{lo}-{hi-1}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for t in all_tcs if lo <= t < hi)
        tc_dist.append({"label": label, "count": cnt})

    result["sec7_3"] = {"years": impact_data, "tc_distribution": tc_dist}
    print(f"  7-3 영향력: 평균TC={round(sum(all_tcs)/max(len(all_tcs),1), 1)}")

    # ── 7-4: 협력 분석 ──
    collab_counter = Counter()
    for r in ibs_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    ibs_collab_orgs = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in ibs_author_uts and rec.get("org_alias") != IBS_ORG_ALIAS:
            oa = rec.get("org_alias", "")
            if oa:
                ibs_collab_orgs[oa] += 1
    top_collab = [{"org": _org_kr(o), "org_en": o, "count": c}
                  for o, c in ibs_collab_orgs.most_common(20)]

    country_counter = Counter()
    for r in ibs_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec7_4"] = {
        "collab_types": dict(collab_counter),
        "top_collab_orgs": top_collab,
        "top_countries": top_countries,
    }
    print(f"  7-4 협력: {dict(collab_counter)}")

    # ── 7-5: 학술지 분석 ──
    journal_counter = Counter()
    for r in ibs_records:
        so = r.get("SO", "")
        if so:
            journal_counter[so] += 1
    top_journals = [{"journal": j, "count": c} for j, c in journal_counter.most_common(30)]

    jif_values = []
    for r in ibs_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry and entry.get("jif"):
            try:
                jif_values.append(float(entry["jif"]))
            except (ValueError, TypeError):
                pass

    jif_bins = [0, 1, 2, 3, 5, 10, 20, 50]
    jif_dist = []
    for i in range(len(jif_bins)):
        lo = jif_bins[i]
        hi = jif_bins[i + 1] if i + 1 < len(jif_bins) else float("inf")
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        cnt = sum(1 for v in jif_values if lo <= v < hi)
        jif_dist.append({"label": label, "count": cnt})

    q1_by_year = defaultdict(lambda: {"q1": 0, "total": 0})
    for r in ibs_records:
        py = r.get("PY", 0)
        if py not in jcr_data:
            continue
        sn = r.get("SN", "").strip()
        ei = r.get("EI", "").strip()
        jcr_yr = jcr_data[py]
        entry = None
        if sn and sn in jcr_yr.get("by_issn", {}):
            entry = jcr_yr["by_issn"][sn]
        elif ei and ei in jcr_yr.get("by_eissn", {}):
            entry = jcr_yr["by_eissn"][ei]
        if entry:
            q1_by_year[py]["total"] += 1
            q = entry.get("quartile", "")
            if isinstance(q, str) and q.startswith("Q1"):
                q1_by_year[py]["q1"] += 1

    q1_trend = []
    for y in years:
        d = q1_by_year.get(y, {"q1": 0, "total": 0})
        ratio = round(d["q1"] / d["total"] * 100, 1) if d["total"] > 0 else 0
        q1_trend.append({"year": y, "q1_ratio": ratio, "q1_count": d["q1"], "total": d["total"]})

    result["sec7_5"] = {
        "top_journals": top_journals,
        "jif_distribution": jif_dist,
        "avg_jif": round(sum(jif_values) / max(len(jif_values), 1), 2),
        "q1_trend": q1_trend,
    }
    print(f"  7-5 학술지: Top1={top_journals[0]['journal'] if top_journals else 'N/A'}, 평균JIF={result['sec7_5']['avg_jif']}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 8: IBS 유발논문분석 (sec5와 동일 로직, IBS 데이터 적용)
# ═══════════════════════════════════════════════════════════
def compute_sec8(ibs_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                 inst_data, ibs_induced_meta, ibs_pure_induced_uts, config: RunConfig):
    print("\n=== 섹션 8: IBS 유발논문분석 ===")
    result = {}
    years = config.years

    # ── 8-1: 유발논문 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in ibs_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        year_data.append({
            "year": y, "count": cnt,
            "kr_share": round(cnt / kr * 100, 3) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec8_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  8-1 현황: {sum(by_year.values()):,}건")

    # ── 8-2: 인프라별 분석 (IBS: 단일 분류 "IBS 연구센터 지원") ──
    infra_total = Counter()
    infra_by_year = defaultdict(lambda: Counter())
    for r in ibs_pure_induced_records:
        infra = "IBS 연구센터 지원"
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            infra_by_year[py][infra] += 1
        infra_total[infra] += 1

    infra_categories = sorted(infra_total.keys(), key=lambda x: infra_total[x], reverse=True)
    infra_year_data = []
    for y in years:
        row = {"year": y}
        for cat in infra_categories:
            row[cat] = infra_by_year[y].get(cat, 0)
        infra_year_data.append(row)

    result["sec8_2"] = {
        "infra_by_year": infra_year_data,
        "infra_total": dict(infra_total),
        "categories": infra_categories,
    }
    print(f"  8-2 인프라별: {dict(infra_total)}")

    # ── 8-3: 수혜기관 분석 ──
    induced_org_counter = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in ibs_pure_induced_uts:
            oa = rec.get("org_alias", "")
            if oa:
                induced_org_counter[oa] += 1

    top_orgs = [{"org": _org_kr(o), "org_en": o, "count": c}
                for o, c in induced_org_counter.most_common(30)]

    org_type_by_ut = defaultdict(set)
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in ibs_pure_induced_uts:
            itype = rec.get("institution_type_7", "기타")
            org_type_by_ut[itype].add(ut)
    org_type_papers = {k: len(v) for k, v in org_type_by_ut.items()}

    result["sec8_3"] = {
        "top_orgs": top_orgs,
        "org_type_papers": org_type_papers,
    }
    print(f"  8-3 수혜기관: Top1={top_orgs[0]['org'] if top_orgs else 'N/A'}")

    # ── 8-4: 분야별 분석 ──
    by_field = Counter()
    for r in ibs_pure_induced_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1

    field_data = []
    ind_total = sum(by_field.values()) or 1
    kr_total = sum(kr_by_field.values()) or 1
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        ind_share = cnt / ind_total
        kr_share = kr_cnt / kr_total
        rca = round(ind_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({"field": f, "count": cnt, "rca": rca})
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec8_4"] = {"fields": field_data}
    print(f"  8-4 분야별: {len([f for f in field_data if f['count'] > 0])}개 활성 분야")

    # ── 8-5: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in ibs_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs), "hcp_count": hcp_count,
        })
    result["sec8_5"] = {"years": impact_data}
    print(f"  8-5 영향력")

    # ── 8-6: 협력 네트워크 ──
    collab_counter = Counter()
    for r in ibs_pure_induced_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    country_counter = Counter()
    for r in ibs_pure_induced_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec8_6"] = {
        "collab_types": dict(collab_counter),
        "top_countries": top_countries,
    }
    print(f"  8-6 협력: {dict(collab_counter)}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 9: KISTI vs IBS 비교 (sec6_1~6_3 복제, sec6_4 인력생산성 제외)
# ═══════════════════════════════════════════════════════════
def compute_sec9(kisti_records, pure_induced_records,
                 ibs_records, ibs_pure_induced_records,
                 kr_by_year, kr_tc_by_year, jcr_data, config: RunConfig):
    print("\n=== 섹션 9: KISTI vs IBS 비교 ===")
    result = {}
    years = config.years

    def _stats(records):
        total = len(records)
        tcs = [r.get("TC", 0) for r in records]
        avg_tc = round(sum(tcs) / max(total, 1), 2)
        q1, jcr_matched = 0, 0
        for r in records:
            py = r.get("PY", 0)
            if py not in jcr_data:
                continue
            sn = r.get("SN", "").strip()
            ei = r.get("EI", "").strip()
            jcr_yr = jcr_data[py]
            entry = None
            if sn and sn in jcr_yr.get("by_issn", {}):
                entry = jcr_yr["by_issn"][sn]
            elif ei and ei in jcr_yr.get("by_eissn", {}):
                entry = jcr_yr["by_eissn"][ei]
            if entry:
                jcr_matched += 1
                q = entry.get("quartile", "")
                if isinstance(q, str) and q.startswith("Q1"):
                    q1 += 1
        q1_ratio = round(q1 / max(jcr_matched, 1) * 100, 1)
        return {"papers": total, "avg_tc": avg_tc, "total_tc": sum(tcs), "q1_ratio": q1_ratio}

    # ── 9-1: 직접 논문 비교 ──
    kisti_stats = _stats(kisti_records)
    ibs_stats = _stats(ibs_records)
    result["sec9_1"] = {"kisti": kisti_stats, "ibs": ibs_stats}
    print(f"  9-1 직접비교: KISTI={kisti_stats['papers']}, IBS={ibs_stats['papers']}")

    # ── 9-2: 유발논문 비교 ──
    kisti_ind_stats = _stats(pure_induced_records)
    ibs_ind_stats = _stats(ibs_pure_induced_records)
    result["sec9_2"] = {"kisti_induced": kisti_ind_stats, "ibs_induced": ibs_ind_stats}
    print(f"  9-2 유발비교: KISTI유발={kisti_ind_stats['papers']}, IBS유발={ibs_ind_stats['papers']}")

    # ── 9-3: 4자 종합 비교 + 연도별 추이 ──
    combined_data = []
    for y in years:
        k_cnt = sum(1 for r in kisti_records if r.get("PY") == y)
        ki_cnt = sum(1 for r in pure_induced_records
                     if isinstance(r.get("PY"), int) and r.get("PY") == y)
        i_cnt = sum(1 for r in ibs_records if r.get("PY") == y)
        ii_cnt = sum(1 for r in ibs_pure_induced_records
                     if isinstance(r.get("PY"), int) and r.get("PY") == y)
        kr = kr_by_year.get(y, 1)
        combined_data.append({
            "year": y,
            "kisti": k_cnt, "kisti_induced": ki_cnt,
            "ibs": i_cnt, "ibs_induced": ii_cnt,
            "kisti_total": k_cnt + ki_cnt,
            "ibs_total": i_cnt + ii_cnt,
            "kisti_kr_share": round((k_cnt + ki_cnt) / kr * 100, 3) if kr else 0,
            "ibs_kr_share": round((i_cnt + ii_cnt) / kr * 100, 3) if kr else 0,
        })

    # 연도별 평균TC 추이
    def _year_avg_tc(records):
        tc_by_y = defaultdict(list)
        for r in records:
            py = r.get("PY", 0)
            if isinstance(py, int) and config.start_year <= py <= config.end_year:
                tc_by_y[py].append(r.get("TC", 0))
        return {y: round(sum(tcs)/max(len(tcs),1), 2) for y, tcs in tc_by_y.items()}

    kisti_tc_trend = _year_avg_tc(kisti_records)
    ibs_tc_trend = _year_avg_tc(ibs_records)
    kisti_ind_tc_trend = _year_avg_tc(pure_induced_records)
    ibs_ind_tc_trend = _year_avg_tc(ibs_pure_induced_records)

    tc_trend_data = []
    for y in years:
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        tc_trend_data.append({
            "year": y,
            "kisti_avg_tc": kisti_tc_trend.get(y, 0),
            "ibs_avg_tc": ibs_tc_trend.get(y, 0),
            "kisti_ind_avg_tc": kisti_ind_tc_trend.get(y, 0),
            "ibs_ind_avg_tc": ibs_ind_tc_trend.get(y, 0),
            "kr_avg_tc": kr_avg,
        })

    result["sec9_3"] = {
        "years": combined_data,
        "tc_trend": tc_trend_data,
        "summary": {
            "kisti": kisti_stats, "kisti_induced": kisti_ind_stats,
            "ibs": ibs_stats, "ibs_induced": ibs_ind_stats,
        },
    }
    print(f"  9-3 종합비교")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 10: PAL(포항가속기연구소) 유발논문분석 (sec5/sec8와 동일 로직)
# ═══════════════════════════════════════════════════════════
def compute_sec10(pal_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                  inst_data, pal_induced_meta, pal_pure_induced_uts, config: RunConfig):
    print("\n=== 섹션 10: PAL 유발논문분석 ===")
    result = {}
    years = config.years

    # ── 10-1: 유발논문 현황 ──
    by_year = Counter()
    by_year_db = defaultdict(lambda: Counter())
    for r in pal_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            by_year[py] += 1
            by_year_db[py][r.get("db", "기타")] += 1

    year_data = []
    for y in years:
        cnt = by_year.get(y, 0)
        kr = kr_by_year.get(y, 1)
        year_data.append({
            "year": y, "count": cnt,
            "kr_share": round(cnt / kr * 100, 3) if kr else 0,
            "scie": by_year_db[y].get("SCIE", 0),
            "ssci": by_year_db[y].get("SSCI", 0),
            "ahci": by_year_db[y].get("AHCI", 0),
        })
    result["sec10_1"] = {"years": year_data, "total": sum(by_year.values())}
    print(f"  10-1 현황: {sum(by_year.values()):,}건")

    # ── 10-2: 인프라별 분석 (PAL: 단일 분류 "PAL 방사광 가속기 지원") ──
    infra_total = Counter()
    infra_by_year = defaultdict(lambda: Counter())
    for r in pal_pure_induced_records:
        infra = "PAL 방사광 가속기 지원"
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            infra_by_year[py][infra] += 1
        infra_total[infra] += 1

    infra_categories = sorted(infra_total.keys(), key=lambda x: infra_total[x], reverse=True)
    infra_year_data = []
    for y in years:
        row = {"year": y}
        for cat in infra_categories:
            row[cat] = infra_by_year[y].get(cat, 0)
        infra_year_data.append(row)

    result["sec10_2"] = {
        "infra_by_year": infra_year_data,
        "infra_total": dict(infra_total),
        "categories": infra_categories,
    }
    print(f"  10-2 인프라별: {dict(infra_total)}")

    # ── 10-3: 수혜기관 분석 ──
    induced_org_counter = Counter()
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in pal_pure_induced_uts:
            oa = rec.get("org_alias", "")
            if oa:
                induced_org_counter[oa] += 1

    top_orgs = [{"org": _org_kr(o), "org_en": o, "count": c}
                for o, c in induced_org_counter.most_common(30)]

    org_type_by_ut = defaultdict(set)
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut in pal_pure_induced_uts:
            itype = rec.get("institution_type_7", "기타")
            org_type_by_ut[itype].add(ut)
    org_type_papers = {k: len(v) for k, v in org_type_by_ut.items()}

    result["sec10_3"] = {
        "top_orgs": top_orgs,
        "org_type_papers": org_type_papers,
    }
    print(f"  10-3 수혜기관: Top1={top_orgs[0]['org'] if top_orgs else 'N/A'}")

    # ── 10-4: 분야별 분석 ──
    by_field = Counter()
    for r in pal_pure_induced_records:
        f = r.get("std_field")
        if f:
            by_field[f] += 1

    field_data = []
    ind_total = sum(by_field.values()) or 1
    kr_total = sum(kr_by_field.values()) or 1
    for f in ESI_22_FIELDS:
        cnt = by_field.get(f, 0)
        kr_cnt = kr_by_field.get(f, 1)
        ind_share = cnt / ind_total
        kr_share = kr_cnt / kr_total
        rca = round(ind_share / kr_share, 2) if kr_share > 0 else 0
        field_data.append({"field": f, "count": cnt, "rca": rca})
    field_data.sort(key=lambda x: x["count"], reverse=True)
    result["sec10_4"] = {"fields": field_data}
    print(f"  10-4 분야별: {len([f for f in field_data if f['count'] > 0])}개 활성 분야")

    # ── 10-5: 영향력 분석 ──
    tc_by_year = defaultdict(list)
    for r in pal_pure_induced_records:
        py = r.get("PY", 0)
        if isinstance(py, int) and config.start_year <= py <= config.end_year:
            tc_by_year[py].append(r.get("TC", 0))

    impact_data = []
    for y in years:
        tcs = tc_by_year.get(y, [])
        avg_tc = round(sum(tcs) / len(tcs), 2) if tcs else 0
        kr_avg = round(kr_tc_by_year.get(y, 0) / kr_by_year.get(y, 1), 2)
        hcp_count = 0
        if tcs:
            sorted_tc = sorted(tcs, reverse=True)
            top1_idx = max(1, int(len(sorted_tc) * 0.01))
            hcp_threshold = sorted_tc[top1_idx - 1] if sorted_tc else 0
            hcp_count = sum(1 for t in tcs if t >= hcp_threshold and t > 0)
        impact_data.append({
            "year": y, "avg_tc": avg_tc, "kr_avg_tc": kr_avg,
            "total_tc": sum(tcs), "paper_count": len(tcs), "hcp_count": hcp_count,
        })
    result["sec10_5"] = {"years": impact_data}
    print(f"  10-5 영향력")

    # ── 10-6: 협력 네트워크 ──
    collab_counter = Counter()
    for r in pal_pure_induced_records:
        collab_counter[r.get("collab_type", "미분류")] += 1

    country_counter = Counter()
    for r in pal_pure_induced_records:
        c1 = r.get("C1", "")
        if not c1:
            continue
        countries = set()
        for block in c1.split("; "):
            parts = block.strip().rstrip(".").split(", ")
            if len(parts) >= 2:
                country = parts[-1].strip().upper()
                if country and country != "SOUTH KOREA" and len(country) >= 4:
                    countries.add(country)
        for c in countries:
            country_counter[c] += 1
    top_countries = [{"country": c, "count": n} for c, n in country_counter.most_common(15)]

    result["sec10_6"] = {
        "collab_types": dict(collab_counter),
        "top_countries": top_countries,
    }
    print(f"  10-6 협력: {dict(collab_counter)}")

    return result


# ═══════════════════════════════════════════════════════════
# 섹션 11: 질적 우수성 종합 비교
# ═══════════════════════════════════════════════════════════

def compute_sec11(kisti_records, pure_induced_records,
                  kbsi_records, kbsi_pure_induced_records,
                  ibs_records, ibs_pure_induced_records,
                  pal_pure_induced_records,
                  kr_by_year, kr_tc_by_year, jcr_data,
                  kr_top10p_by_year, kr_top10p_by_year_field,
                  kr_avg_tc_by_year_field, sec2_7,
                  config: RunConfig):
    """질적 우수성 종합 비교 — 4개 기관 질적 지표 일괄 비교"""
    print("\n=== 섹션 11: 질적 우수성 종합 비교 ===")
    result = {}
    years = config.years

    # ── 공통 유틸 ──
    def _avg_tc(records):
        if not records:
            return 0.0
        tcs = [r.get("TC", 0) for r in records]
        return round(sum(tcs) / len(tcs), 2)

    def _top10p_ratio(records, thresholds):
        if not thresholds or not records:
            return 0.0, 0, len(records)
        top10_cnt = 0
        for r in records:
            py = r.get("PY", 0)
            tc = r.get("TC", 0)
            thr = thresholds.get(py, float("inf"))
            if tc >= thr and tc > 0:
                top10_cnt += 1
        total = len(records)
        return round(top10_cnt / max(total, 1) * 100, 1), top10_cnt, total

    def _top10p_field_ratio(records, thresholds_yf):
        if not thresholds_yf or not records:
            return 0.0, 0, len(records)
        top10_cnt = 0
        valid_cnt = 0
        for r in records:
            py = r.get("PY", 0)
            f = r.get("std_field")
            if not f:
                continue
            valid_cnt += 1
            tc = r.get("TC", 0)
            yr_fields = thresholds_yf.get(py, {})
            thr = yr_fields.get(f, float("inf"))
            if tc >= thr and tc > 0:
                top10_cnt += 1
        return round(top10_cnt / max(valid_cnt, 1) * 100, 1), top10_cnt, valid_cnt

    def _q1_ratio(records):
        q1, matched = 0, 0
        for r in records:
            py = r.get("PY", 0)
            if py not in jcr_data:
                continue
            sn = r.get("SN", "").strip()
            ei = r.get("EI", "").strip()
            jcr_yr = jcr_data[py]
            entry = None
            if sn and sn in jcr_yr.get("by_issn", {}):
                entry = jcr_yr["by_issn"][sn]
            elif ei and ei in jcr_yr.get("by_eissn", {}):
                entry = jcr_yr["by_eissn"][ei]
            if not entry:
                continue
            matched += 1
            q = entry.get("quartile", "")
            if isinstance(q, str) and q.startswith("Q1"):
                q1 += 1
        return round(q1 / max(matched, 1) * 100, 1), q1, matched

    def _mncs(records):
        if not kr_avg_tc_by_year_field or not records:
            return None, 0
        total_ncs = 0.0
        valid = 0
        for r in records:
            py = r.get("PY", 0)
            f = r.get("std_field")
            if not f:
                continue
            kr_avg = (kr_avg_tc_by_year_field.get(py, {}) or {}).get(f, 0)
            if kr_avg <= 0:
                continue
            valid += 1
            total_ncs += r.get("TC", 0) / kr_avg
        if valid == 0:
            return None, 0
        return round(total_ncs / valid, 3), valid

    # ── 기관별 질적 지표 계산 ──
    institutions = []
    all_sets = [
        ("KISTI", "직접", kisti_records),
        ("KISTI", "유발", pure_induced_records),
        ("KBSI", "직접", kbsi_records),
        ("KBSI", "유발", kbsi_pure_induced_records),
        ("IBS", "직접", ibs_records),
        ("IBS", "유발", ibs_pure_induced_records),
        ("PAL", "유발", pal_pure_induced_records),
    ]

    for name, ptype, records in all_sets:
        avg_tc = _avg_tc(records)
        t10_ratio, t10_cnt, t10_total = _top10p_ratio(records, kr_top10p_by_year)
        ft10_ratio, ft10_cnt, ft10_valid = _top10p_field_ratio(records, kr_top10p_by_year_field)
        q1_ratio, q1_cnt, q1_matched = _q1_ratio(records)
        mncs_val, mncs_valid = _mncs(records)

        institutions.append({
            "name": name,
            "type": ptype,
            "papers": len(records),
            "avg_tc": avg_tc,
            "mncs": mncs_val,
            "mncs_matched": mncs_valid,
            "top10p_ratio": t10_ratio,
            "top10p_count": t10_cnt,
            "ftop10p_ratio": ft10_ratio,
            "ftop10p_count": ft10_cnt,
            "q1_ratio": q1_ratio,
            "q1_count": q1_cnt,
            "q1_matched": q1_matched,
        })
        print(f"  {name} {ptype}: {len(records):,}건, "
              f"평균TC={avg_tc}, MNCS={mncs_val}, "
              f"상위10%(분야)={ft10_ratio}%, Q1={q1_ratio}%")

    # ── 레버리지 (유발/직접 비율) ──
    leverage = []
    for name, direct, induced in [
        ("KISTI", kisti_records, pure_induced_records),
        ("KBSI", kbsi_records, kbsi_pure_induced_records),
        ("IBS", ibs_records, ibs_pure_induced_records),
    ]:
        d_cnt = len(direct)
        i_cnt = len(induced)
        leverage.append({
            "name": name,
            "direct": d_cnt,
            "induced": i_cnt,
            "combined": d_cnt + i_cnt,
            "ratio": round(i_cnt / max(d_cnt, 1), 2),
        })

    # ── 예산 효율 (sec2_7에서 가져옴) ──
    budget = None
    if sec2_7:
        bn = sec2_7.get("budget_normalized", {})
        budget = {
            "annual_budget_10b": bn.get("kisti_annual_10b"),
            "papers_per_10b_yr": bn.get("papers_per_10b_yr"),
            "citations_per_10b_yr": bn.get("citations_per_10b_yr"),
            "mncs": sec2_7.get("mncs"),
            "roi_low": sec2_7.get("roi_low"),
            "roi_high": sec2_7.get("roi_high"),
        }

    # ── 연도별 평균TC 추이 (4기관 직접+유발) ──
    def _tc_by_year(records):
        by_y = defaultdict(list)
        for r in records:
            by_y[r.get("PY", 0)].append(r.get("TC", 0))
        return by_y

    k_tc = _tc_by_year(kisti_records)
    ki_tc = _tc_by_year(pure_induced_records)
    b_tc = _tc_by_year(kbsi_records)
    bi_tc = _tc_by_year(kbsi_pure_induced_records)
    ibs_tc = _tc_by_year(ibs_records)
    ibsi_tc = _tc_by_year(ibs_pure_induced_records)
    pal_tc = _tc_by_year(pal_pure_induced_records)

    def _yr_avg(tc_dict, y):
        tcs = tc_dict.get(y, [])
        return round(sum(tcs) / len(tcs), 2) if tcs else 0

    tc_trend = []
    for y in years:
        kr_avg = round((kr_tc_by_year.get(y, 0)) / max(kr_by_year.get(y, 1), 1), 2)
        tc_trend.append({
            "year": y,
            "kr_avg_tc": kr_avg,
            "kisti_direct": _yr_avg(k_tc, y),
            "kisti_induced": _yr_avg(ki_tc, y),
            "kbsi_direct": _yr_avg(b_tc, y),
            "kbsi_induced": _yr_avg(bi_tc, y),
            "ibs_direct": _yr_avg(ibs_tc, y),
            "ibs_induced": _yr_avg(ibsi_tc, y),
            "pal_induced": _yr_avg(pal_tc, y),
        })

    result["sec11_1"] = {
        "institutions": institutions,
        "leverage": leverage,
        "budget": budget,
        "tc_trend": tc_trend,
    }

    print(f"  11-1 질적비교: {len(institutions)}개 기관·유형")

    return result


# ═══════════════════════════════════════════════════════════
# 논문별 레코드 빌드 (프론트엔드 논문관리 페이지용)
# ═══════════════════════════════════════════════════════════
def _lookup_jif(r, jcr_data):
    """JIF와 quartile 조회"""
    py = r.get("PY", 0)
    if py not in jcr_data:
        return None, None
    sn = r.get("SN", "").strip()
    ei = r.get("EI", "").strip()
    jcr_yr = jcr_data[py]
    entry = None
    if sn and sn in jcr_yr.get("by_issn", {}):
        entry = jcr_yr["by_issn"][sn]
    elif ei and ei in jcr_yr.get("by_eissn", {}):
        entry = jcr_yr["by_eissn"][ei]
    if not entry:
        return None, None
    jif = None
    try:
        jif = float(entry.get("jif", 0))
    except (ValueError, TypeError):
        pass
    q = entry.get("quartile", "")
    return jif, q if isinstance(q, str) else None


def _parse_countries(c1):
    """C1 필드에서 국가 목록 추출"""
    if not c1:
        return []
    countries = set()
    for block in c1.split("; "):
        parts = block.strip().rstrip(".").split(", ")
        if len(parts) >= 2:
            country = parts[-1].strip().upper()
            if country:
                countries.add(country)
    return sorted(countries)


def _extract_orgs(ut, inst_data_by_ut):
    """inst_data에서 해당 UT의 기관 목록 추출"""
    recs = inst_data_by_ut.get(ut, [])
    orgs = []
    seen = set()
    for rec in recs:
        oa = rec.get("org_alias", "")
        if not oa or oa in seen:
            continue
        seen.add(oa)
        orgs.append({
            "org_alias": oa,
            "org_kr": _org_kr(oa),
            "type7": rec.get("institution_type_7", "기타"),
        })
    return orgs


def build_paper_records(kisti_records, pure_induced_records,
                        kbsi_records, kbsi_pure_induced_records,
                        ibs_records, ibs_pure_induced_records,
                        pal_pure_induced_records,
                        inst_data, jcr_data):
    """논문별 레코드 빌드 (프론트엔드 테이블/모달용)"""
    print("\n=== 논문별 레코드 빌드 ===")

    # inst_data를 UT별 인덱싱
    inst_by_ut = defaultdict(list)
    for rec in inst_data:
        ut = rec.get("UT", "")
        if ut:
            inst_by_ut[ut].append(rec)

    def _build_direct_papers(records, label):
        papers = []
        for r in records:
            ut = r.get("UT", "")
            jif, q = _lookup_jif(r, jcr_data)
            papers.append({
                "UT": ut,
                "PY": r.get("PY", 0),
                "TI": r.get("TI", ""),
                "TC": r.get("TC", 0),
                "SO": r.get("SO", ""),
                "db": r.get("db", ""),
                "std_field": r.get("std_field"),
                "collab_type": r.get("collab_type", "미분류"),
                "jif": jif,
                "quartile": q,
                "countries": _parse_countries(r.get("C1", "")),
                "orgs": _extract_orgs(ut, inst_by_ut),
            })
        print(f"  {label} 논문 레코드: {len(papers):,}건")
        return papers

    def _build_induced_papers(records, infra_classify_fn, label):
        papers = []
        for r in records:
            ut = r.get("UT", "")
            jif, q = _lookup_jif(r, jcr_data)
            meta = r.get("_induced_meta", {})
            kws = meta.get("keywords", [])
            infra = infra_classify_fn(kws)
            papers.append({
                "UT": ut,
                "PY": r.get("PY", 0),
                "TC": r.get("TC", 0),
                "SO": r.get("SO", ""),
                "TI": r.get("TI", meta.get("TI", "")),
                "db": r.get("db", meta.get("db", "")),
                "std_field": r.get("std_field"),
                "collab_type": r.get("collab_type", "미분류"),
                "jif": jif,
                "quartile": q,
                "countries": _parse_countries(r.get("C1", "")),
                "orgs": _extract_orgs(ut, inst_by_ut),
                "infra_type": infra,
                "keywords": kws,
                "FU": r.get("FU", meta.get("FU", "")),
                "FX": r.get("FX", meta.get("FX", "")),
            })
        print(f"  {label} 유발논문 레코드: {len(papers):,}건")
        return papers

    kisti_papers = _build_direct_papers(kisti_records, "KISTI")
    induced_papers = _build_induced_papers(pure_induced_records, classify_infra, "KISTI")
    kbsi_papers = _build_direct_papers(kbsi_records, "KBSI")
    kbsi_induced_papers_recs = _build_induced_papers(
        kbsi_pure_induced_records,
        lambda kws: "KBSI 분석장비 지원",
        "KBSI"
    )
    ibs_papers = _build_direct_papers(ibs_records, "IBS")
    ibs_induced_papers_recs = _build_induced_papers(
        ibs_pure_induced_records,
        lambda kws: "IBS 연구센터 지원",
        "IBS"
    )
    pal_induced_papers_recs = _build_induced_papers(
        pal_pure_induced_records,
        lambda kws: "PAL 방사광 가속기 지원",
        "PAL"
    )

    return (kisti_papers, induced_papers, kbsi_papers, kbsi_induced_papers_recs,
            ibs_papers, ibs_induced_papers_recs, pal_induced_papers_recs)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════
def main():
    print("KISTI Policy 분석 데이터 생성")
    print("=" * 60)

    # 설정 빌드
    config = parse_args()
    if config is None:
        config = interactive_config(DEFAULT_BASE)

    print(f"\n설정: 버전={config.data_version}, 기간={config.period_str}, "
          f"스냅샷={config.snapshot or '없음'}")
    print(f"출력: {config.output}")
    print("=" * 60)

    wos_data, inst_data, jcr_data, induced_papers, kbsi_induced_papers, ibs_induced_papers, pal_induced_papers, gri_personnel = load_data(config)
    (wos_by_ut, kisti_records, pure_induced_records, induced_meta,
     kisti_author_uts, pure_induced_uts,
     kbsi_records, kbsi_pure_induced_records, kbsi_induced_meta,
     kbsi_author_uts, kbsi_pure_induced_uts,
     ibs_records, ibs_pure_induced_records, ibs_induced_meta,
     ibs_author_uts, ibs_pure_induced_uts,
     pal_pure_induced_records, pal_induced_meta, pal_pure_induced_uts) = classify_papers(
        wos_data, inst_data, induced_papers, kbsi_induced_papers, ibs_induced_papers, pal_induced_papers
    )
    (kr_by_year, kr_tc_by_year, kr_by_field, kr_count,
     kr_top10p_by_year, kr_top10p_by_year_field,
     kr_avg_tc_by_year_field) = compute_korea_stats(wos_data, config)

    # Free wos_data from memory after extracting what we need
    del wos_data

    sec1 = compute_sec1(kisti_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, jcr_data, wos_by_ut, kisti_author_uts, config)
    sec2 = compute_sec2(pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, induced_meta, pure_induced_uts,
                        kr_avg_tc_by_year_field, config)
    sec3 = compute_sec3(kisti_records, pure_induced_records, kr_by_year, kr_tc_by_year,
                        jcr_data, config)
    sec4 = compute_sec4(kbsi_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, jcr_data, wos_by_ut, kbsi_author_uts, config)
    sec5 = compute_sec5(kbsi_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, kbsi_induced_meta, kbsi_pure_induced_uts, config)
    sec6 = compute_sec6(kisti_records, pure_induced_records,
                        kbsi_records, kbsi_pure_induced_records,
                        kr_by_year, kr_tc_by_year, jcr_data,
                        gri_personnel, kr_top10p_by_year,
                        kr_top10p_by_year_field, config)
    sec7 = compute_sec7(ibs_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, jcr_data, wos_by_ut, ibs_author_uts, config)
    sec8 = compute_sec8(ibs_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                        inst_data, ibs_induced_meta, ibs_pure_induced_uts, config)
    sec9 = compute_sec9(kisti_records, pure_induced_records,
                        ibs_records, ibs_pure_induced_records,
                        kr_by_year, kr_tc_by_year, jcr_data, config)
    sec10 = compute_sec10(pal_pure_induced_records, kr_by_year, kr_tc_by_year, kr_by_field,
                          inst_data, pal_induced_meta, pal_pure_induced_uts, config)
    sec11 = compute_sec11(kisti_records, pure_induced_records,
                          kbsi_records, kbsi_pure_induced_records,
                          ibs_records, ibs_pure_induced_records,
                          pal_pure_induced_records,
                          kr_by_year, kr_tc_by_year, jcr_data,
                          kr_top10p_by_year, kr_top10p_by_year_field,
                          kr_avg_tc_by_year_field, sec2.get("sec2_7"),
                          config)

    # 논문별 레코드 빌드
    (kisti_paper_recs, induced_paper_recs, kbsi_paper_recs, kbsi_induced_paper_recs,
     ibs_paper_recs, ibs_induced_paper_recs, pal_induced_paper_recs) = \
        build_paper_records(kisti_records, pure_induced_records,
                           kbsi_records, kbsi_pure_induced_records,
                           ibs_records, ibs_pure_induced_records,
                           pal_pure_induced_records,
                           inst_data, jcr_data)

    # 요약 카드 데이터
    summary = {
        "kisti_papers": len(kisti_records),
        "induced_papers": len(pure_induced_records),
        "kisti_avg_tc": round(sum(r.get("TC", 0) for r in kisti_records) / max(len(kisti_records), 1), 1),
        "induced_avg_tc": round(sum(r.get("TC", 0) for r in pure_induced_records) / max(len(pure_induced_records), 1), 1),
        "kr_total": kr_count,
        "kisti_kr_share": round(len(kisti_records) / max(kr_count, 1) * 100, 2),
        "combined_kr_share": round((len(kisti_records) + len(pure_induced_records)) / max(kr_count, 1) * 100, 2),
        "kbsi_papers": len(kbsi_records),
        "kbsi_induced_papers": len(kbsi_pure_induced_records),
        "kbsi_avg_tc": round(sum(r.get("TC", 0) for r in kbsi_records) / max(len(kbsi_records), 1), 1),
        "kbsi_induced_avg_tc": round(sum(r.get("TC", 0) for r in kbsi_pure_induced_records) / max(len(kbsi_pure_induced_records), 1), 1),
        "kbsi_kr_share": round(len(kbsi_records) / max(kr_count, 1) * 100, 2),
        "kbsi_combined_kr_share": round((len(kbsi_records) + len(kbsi_pure_induced_records)) / max(kr_count, 1) * 100, 2),
        "ibs_papers": len(ibs_records),
        "ibs_induced_papers": len(ibs_pure_induced_records),
        "ibs_avg_tc": round(sum(r.get("TC", 0) for r in ibs_records) / max(len(ibs_records), 1), 1),
        "ibs_induced_avg_tc": round(sum(r.get("TC", 0) for r in ibs_pure_induced_records) / max(len(ibs_pure_induced_records), 1), 1),
        "ibs_kr_share": round(len(ibs_records) / max(kr_count, 1) * 100, 2),
        "ibs_combined_kr_share": round((len(ibs_records) + len(ibs_pure_induced_records)) / max(kr_count, 1) * 100, 2),
        "pal_induced_papers": len(pal_pure_induced_records),
        "pal_induced_avg_tc": round(sum(r.get("TC", 0) for r in pal_pure_induced_records) / max(len(pal_pure_induced_records), 1), 1),
        "pal_induced_kr_share": round(len(pal_pure_induced_records) / max(kr_count, 1) * 100, 2),
    }

    data_cache = {
        "_meta": {
            "data_version": config.data_version,
            "analysis_period": config.period_str,
            "start_year": config.start_year,
            "end_year": config.end_year,
            "num_years": config.num_years,
            "snapshot": config.snapshot,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "summary": summary,
        **sec1,
        **sec2,
        **sec3,
        **sec4,
        **sec5,
        **sec6,
        **sec7,
        **sec8,
        **sec9,
        **sec10,
        **sec11,
        "papers": {
            "kisti": kisti_paper_recs,
            "induced": induced_paper_recs,
            "kbsi": kbsi_paper_recs,
            "kbsi_induced": kbsi_induced_paper_recs,
            "ibs": ibs_paper_recs,
            "ibs_induced": ibs_induced_paper_recs,
            "pal_induced": pal_induced_paper_recs,
        },
        "korea": {
            "by_year": kr_by_year,
            "tc_by_year": kr_tc_by_year,
            "by_field": kr_by_field,
            "top10p_by_year": kr_top10p_by_year,
            "top10p_by_year_field": kr_top10p_by_year_field,
            "avg_tc_by_year_field": kr_avg_tc_by_year_field,
        },
    }

    # int keys → str for JSON
    def _convert(obj):
        if isinstance(obj, dict):
            return {str(k): _convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_convert(i) for i in obj]
        if isinstance(obj, (int,)):
            return obj
        if isinstance(obj, float):
            if obj != obj:  # NaN
                return 0
            return obj
        return obj

    data_cache = _convert(data_cache)

    json_text = json.dumps(data_cache, ensure_ascii=False, indent=1)

    # 버전별 파일 저장
    versioned_out = Path(__file__).parent / f"data_cache_{config.data_version}.json"
    versioned_out.write_text(json_text, encoding="utf-8")
    print(f"\n=== 버전별 파일: {versioned_out} ({versioned_out.stat().st_size / 1024 / 1024:.1f} MB) ===")

    # 기본 data_cache.json 에도 저장 (하위 호환)
    default_out = Path(__file__).parent / "data_cache.json"
    default_out.write_text(json_text, encoding="utf-8")
    print(f"=== 기본 파일: {default_out} ===")


if __name__ == "__main__":
    main()
