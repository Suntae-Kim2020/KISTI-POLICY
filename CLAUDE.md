# KISTI Policy 분석 대시보드

## 프로젝트 목적

KISTI(한국과학기술정보연구원)의 논문 성과와 인프라 유발 효과를 분석하는 독립 웹 서비스.
기존 KISTEP 보고서 도구(`/Users/kimsuntae/KISTEP/`)와 별도로 운영된다.

---

## 세 가지 분석 축

1. **KISTI 논문** — KISTI 소속 저자가 포함되었으나 사사표기(FU/FX)에 KISTI 인프라 키워드가 **없는** 논문 (`inst_data`에서 `org_alias = "KOREA INST SCI & TECHNOL INFORMAT"`, 사사표기 중복 제외)
2. **KISTI 유발논문** — 사사표기(FU/FX)에 KISTI 인프라 키워드가 검출된 **모든** 논문 (`kisti_induced_papers.json` 기반). KISTI 소속 공저자가 있어도 사사표기가 있으면 유발논문으로 분류
3. **IBS 논문/유발논문** — IBS(기초과학연구원) 소속 논문 (`org_alias = "INST BASIC SCI KOREA"`) 및 사사표기에 IBS 키워드가 검출된 유발논문 (`ibs_induced_papers.json` 기반). KISTI/KBSI와 동일한 분류 원칙 적용. IBS는 NST 소관이 아니므로 인력 생산성 분석(sec6_4) 대상에서 제외

---

## 파일 구조

```
KISTI_Policy/
├── CLAUDE.md                    # 이 파일
├── compute.py                   # 데이터 전처리: pickle 로딩 → 분석 → data_cache.json 생성
├── app.py                       # Flask 서버 (port 5002)
├── scan_kbsi_induced.py         # KBSI 유발논문 탐색 → kbsi_induced_papers.json 생성
├── scan_ibs_induced.py          # IBS 유발논문 탐색 → ibs_induced_papers.json 생성
├── scan_pal_induced.py          # PAL 유발논문 탐색 → pal_induced_papers.json 생성
├── data_cache.json              # compute.py 실행 결과 (~51MB, 생성 파일)
├── exclusions.json              # 대시보드에서 제외한 논문 UT 목록
├── 파일목록_참고자료.txt           # 전체 파일 목록 및 용도 상세 설명
├── generated/
│   ├── cdn/                     # CDN JS 캐시 (chart.js, datalabels)
│   └── html/                    # 독립 실행 라이브차트 HTML
├── rawdata/
│   └── 국가과학기술연구회 소관 출연연 학위별 인력 정보(정규인력 전체)_20211231.csv
│                                # NST 소관 25개 출연연 학위별 인력 (CP949, sec6_4용)
└── templates/
    └── dashboard.html           # 싱글 페이지 대시보드 (Chart.js, 다크 테마, 52개 페이지)
```

### KISTEP 폴더 구조 (`/Users/kimsuntae/KISTEP/`)

```
KISTEP/
├── rawdata/                    # 원본 소스 데이터 (WoS TXT, JCR Excel 등)
│   ├── wos/                    # WoS 원시 TXT 파일 (한국 SCIE 논문)
│   ├── jcr/                    # JCR Excel 파일 (Journal Impact Factor)
│   ├── institutions/           # 기관 분류 데이터
│   ├── esi/                    # ESI 저널-분야 매핑 원본
│   ├── hcp/                    # Highly Cited Papers 데이터
│   ├── incites/                # InCites 분석 데이터
│   └── external/               # 외부 참고 자료
├── generated/                  # 중간 생성물 (pickle 파일)
│   ├── 2024/                   # 2024년 기준 생성
│   ├── 2025/                   # 2025년 기준 생성
│   └── master/                 # 최신 마스터
├── *.pkl → generated/*.pkl     # 심볼릭 링크 (compute.py가 루트에서 참조)
├── kisti_induced_papers.json   # KISTI 유발논문 UT 목록 (6,307건)
├── kbsi_induced_papers.json    # KBSI 유발논문 UT 목록 (7,810건)
├── ibs_induced_papers.json     # IBS 유발논문 UT 목록 (8,294건, scan_ibs_induced.py로 생성)
├── kisti_induced_summary.json  # KISTI 유발논문 인프라별 건수 요약
└── preprocess_wos.py           # WoS TXT → pickle 변환 스크립트
```

**소스 데이터** (rawdata/): WoS에서 다운로드한 원시 TXT, JCR Excel 등 원본 파일.
**중간 생성물** (generated/): `preprocess_wos.py`가 원본 TXT를 파싱하여 생성한 pickle 파일. compute.py가 이 pickle을 로딩.

| 파일 (심볼릭 링크) | 용량 | 용도 |
|------|------|------|
| `wos_data.pkl` | 931MB | WoS 논문 메타데이터 (~96만건). preprocess_wos.py로 생성 |
| `wos_institutions.pkl` | 580MB | WoS 기관 데이터 (~281만건). 논문-기관 매핑 |
| `jcr_jif.pkl` | 35MB | JCR Journal Impact Factor. 학술지 분석·Q1-Q4 분위 |
| `esi_journal_map.pkl` | 312KB | ESI 저널-분야 매핑 (ISSN → 22개 분야) |
| `kr_journals.pkl` | 15KB | 한국 저널 목록 |
| `multi_reclass.pkl` | 5B | Multidisciplinary 재분류 (현재 미적용, 빈 파일) |
| `kisti_induced_papers.json` | 9.5MB | KISTI 유발논문 UT 목록 (6,307건) |
| `kbsi_induced_papers.json` | 7.3MB | KBSI 유발논문 UT 목록 (scan_kbsi_induced.py로 생성) |
| `ibs_induced_papers.json` | 8.4MB | IBS 유발논문 UT 목록 (8,294건, scan_ibs_induced.py로 생성) |
| `pal_induced_papers.json` | 3.3MB | PAL 유발논문 UT 목록 (3,123건, scan_pal_induced.py로 생성) |
| `kisti_induced_summary.json` | 545B | KISTI 유발논문 인프라별 건수 요약 |

---

## 데이터 흐름

```
[소스 데이터: KISTEP/rawdata/]
  WoS TXT, JCR Excel, ESI 분류표 등
       │
       ▼
(KISTEP/preprocess_wos.py)
       │
       ▼
[중간 생성물: KISTEP/generated/]           [유발논문 JSON: KISTEP/]
  wos_data.pkl, wos_institutions.pkl        kisti_induced_papers.json
  jcr_jif.pkl, esi_journal_map.pkl          kbsi_induced_papers.json
                                            ibs_induced_papers.json
                                            pal_induced_papers.json
       │               │                          │
       └───────── *.pkl 심볼릭 링크 ──────────────┤
                                                   │
  rawdata/출연연 인력 CSV ─────────────────────────┤
                                                   ▼
                                      (KISTI_Policy/compute.py)
                                                   │
                                                   ▼
                                          data_cache.json
                                                   │
                                      (KISTI_Policy/app.py → port 5002)
                                                   │
                                                   ▼
                                      대시보드 (dashboard.html)
```

---

## 사용 방법

```bash
# 1. 데이터 캐시 생성 (KISTEP 폴더의 pickle 필요, ~3-4GB RAM, ~2분)
python3 KISTI_Policy/compute.py

# 2. 대시보드 실행
python3 KISTI_Policy/app.py
# → http://localhost:5002 접속
```

### 전제조건

- `/Users/kimsuntae/KISTEP/` 루트에 pickle 심볼릭 링크가 존재해야 함 (`generated/`의 실제 파일을 가리킴)
- `/Users/kimsuntae/KISTEP/`에 유발논문 JSON 파일 존재
- Python 패키지: `flask`

---

## 데이터 파이프라인 (compute.py)

### 1단계: 데이터 로딩
- KISTEP 루트의 pickle 심볼릭 링크 6개 + 유발논문 JSON 4개 로딩 (실제 파일은 `generated/`)
- `rawdata/` 폴더에서 출연연 인력 CSV 로딩
- ESI ISSN 기반 `std_field` 재매핑
- `institution_type_7` 재분류 (정부부처→국공립연구소, 27,088건)

### 2단계: 논문 그룹 분류

**분류 원칙**: 사사표기(FU/FX)에 인프라 키워드가 있으면 소속 공저자 유무와 무관하게 **유발논문으로 분류**. 중복분(소속+사사)은 직접논문에서 제외.

```
KISTI 소속 UT (inst_data에서 org_alias 매칭)
  → 2,580건 (Article 필터 후)
  → 중복(소속+사사) 624건 → 유발논문으로 이동
  → kisti_author_uts: 1,956건 (직접논문)

KISTI 유발논문 UT (kisti_induced_papers.json, 사사표기 기반)
  → induced_json_uts: 6,161건 (사사 있으면 전부 유발논문)
  → wos_data 매칭: 6,104건

KBSI 소속 UT → 6,832건 → 중복 2,345건 제외 → kbsi_author_uts: 4,487건
KBSI 유발논문 UT → kbsi_induced: 7,810건

IBS 소속 UT (inst_data에서 org_alias = "INST BASIC SCI KOREA")
  → 9,223건 (Article 필터 후)
  → 중복(소속+사사) 6,617건 → 유발논문으로 이동
  → ibs_author_uts: 2,606건 (직접논문)

IBS 유발논문 UT (ibs_induced_papers.json, 사사표기 기반)
  → ibs_induced_json_uts: 8,294건
  → wos_data 매칭: 8,290건
```

### 3단계: 섹션별 통계 계산 (52개 페이지)
- 한국 전체 통계 (연도별·분야별 TC 분포, 상위 10% 임계값, 연도×분야별 평균TC)
- `compute_korea_stats()` → 7-tuple 반환: `kr_by_year`, `kr_tc_by_year`, `kr_by_field`, `kr_count`, `kr_top10p_by_year`, `kr_top10p_by_year_field`, `kr_avg_tc_by_year_field`
- sec1_1~sec1_5: KISTI 논문 5개 분석
- sec2_1~sec2_8: KISTI 유발논문 8개 분석 (경제적 가치, MNCS, 예산 정규화, 국제 비교 포함)
- sec3_1~sec3_3: KISTI 비교·종합 3개 분석
- sec4_1~sec4_5: KBSI 논문 5개 분석
- sec5_1~sec5_6: KBSI 유발논문 6개 분석
- sec6_1~sec6_4: KISTI vs KBSI 비교 4개 분석 (인력 생산성 포함)
- sec7_1~sec7_5: IBS 논문 5개 분석
- sec8_1~sec8_6: IBS 유발논문 6개 분석
- sec9_1~sec9_3: KISTI vs IBS 비교 3개 분석 (인력 생산성 제외 — IBS는 NST 소관 아님)
- sec10_1~sec10_6: PAL 유발논문 6개 분석 (직접논문 없음 — PAL은 POSTECH 하위기관으로 WoS org_alias 분리 불가)

### 4단계: `data_cache.json` 출력
- Flask는 이 JSON만 로딩하여 서빙 (pickle 재로딩 불필요)
- `korea.top10p_by_year`, `korea.top10p_by_year_field` 포함 (재계산용)

---

## 메뉴 구조 및 차트 (52개 페이지)

### 개요
- 요약 대시보드: KISTI/KBSI/IBS 요약 카드 3행 + 연도별 합산 차트 + 3-way 비교 차트 + 논문 관리

### 섹션 1: KISTI 논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec1_1` | 발표 현황 | Stacked Bar(DB별 연도별) + Line(성장률) + Line(한국 비중) |
| `sec1_2` | 분야별 현황 | Horizontal Bar(22분야) + Radar(RCA 상위12) |
| `sec1_3` | 영향력 분석 | Line(KISTI vs 한국 평균TC) + Bar(HCP) + Bar(TC분포) |
| `sec1_4` | 협력 분석 | Doughnut(협력유형) + Bar(협력국 Top15) + H-Bar(기관 Top20) |
| `sec1_5` | 학술지 분석 | H-Bar(학술지 Top30) + Bar(JIF분포) + Line(Q1비율 추이) |

### 섹션 2: KISTI 유발논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec2_1` | 유발논문 현황 | Stacked Bar(연도별) + Line(한국 비중) |
| `sec2_2` | 인프라별 분석 | Doughnut(비율) + Stacked Bar(연도 추이) + 테이블 |
| `sec2_3` | 수혜기관 분석 | Doughnut(기관유형) + H-Bar(기관 Top30) |
| `sec2_4` | 분야별 분석 | H-Bar(22분야) + Radar(RCA 상위12) |
| `sec2_5` | 영향력 분석 | Line(유발 vs 한국 평균TC) + Bar(HCP) |
| `sec2_6` | 협력 네트워크 | Doughnut(협력유형) + Bar(협력국 Top15) |
| `sec2_7` | 경제적 가치 추정 | H-Bar(대체가치) + Bar(ROI) + Bar(MNCS) + Line(MNCS 추이) + H-Bar(예산 정규화) + 요약 테이블 |
| `sec2_8` | 국제 비교 | **[핵심] 기간매칭비교**: 겹치는 기간만 추출하여 Grouped Bar + 비교표 (caveat 경고 포함) / **[참고] 전체기간**: Bar(논문수/예산/ROI/피인용) + 종합표 |

### 섹션 3: KISTI 비교·종합

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec3_1` | KISTI vs 유발논문 | Grouped Bar(지표 비교) + 비교 테이블 |
| `sec3_2` | 기여도 종합 | Stacked Bar(직접+유발 연도별) + Line(한국 비중) |
| `sec3_3` | 인프라 투자 효과 | Multi-Line(논문수 추이) + Multi-Line(평균TC 추이) |

### 섹션 4: KBSI 논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec4_1` | 발표 현황 | Stacked Bar(DB별 연도별) + Line(성장률) + Line(한국 비중) |
| `sec4_2` | 분야별 현황 | Horizontal Bar(22분야) + Radar(RCA 상위12) |
| `sec4_3` | 영향력 분석 | Line(KBSI vs 한국 평균TC) + Bar(HCP) + Bar(TC분포) |
| `sec4_4` | 협력 분석 | Doughnut(협력유형) + Bar(협력국 Top15) + H-Bar(기관 Top20) |
| `sec4_5` | 학술지 분석 | H-Bar(학술지 Top30) + Bar(JIF분포) + Line(Q1비율 추이) |

### 섹션 5: KBSI 유발논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec5_1` | 유발논문 현황 | Stacked Bar(연도별) + Line(한국 비중) |
| `sec5_2` | 인프라별 분석 | Doughnut(비율) + Stacked Bar(연도 추이) + 테이블 |
| `sec5_3` | 수혜기관 분석 | Doughnut(기관유형) + H-Bar(기관 Top30) |
| `sec5_4` | 분야별 분석 | H-Bar(22분야) + Radar(RCA 상위12) |
| `sec5_5` | 영향력 분석 | Line(유발 vs 한국 평균TC) + Bar(HCP) |
| `sec5_6` | 협력 네트워크 | Doughnut(협력유형) + Bar(협력국 Top15) |

### 섹션 6: KISTI vs KBSI 비교

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec6_1` | 직접 논문 비교 | Grouped Bar(연도별) + 비교 테이블 |
| `sec6_2` | 유발논문 비교 | Grouped Bar(연도별) + 비교 테이블 |
| `sec6_3` | 종합 비교 | Grouped Bar(지표) + Stacked Bar(연도별) + 비교 테이블 |
| `sec6_4` | 인력 생산성 분석 | Grouped Bar(인력/생산성/상위10%/Q1-Q4) + H-Bar(25개 출연연) |

### 섹션 7: IBS 논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec7_1` | 발표 현황 | Stacked Bar(DB별 연도별) + Line(성장률) + Line(한국 비중) |
| `sec7_2` | 분야별 현황 | Horizontal Bar(22분야) + Radar(RCA 상위12) |
| `sec7_3` | 영향력 분석 | Line(IBS vs 한국 평균TC) + Bar(HCP) + Bar(TC분포) |
| `sec7_4` | 협력 분석 | Doughnut(협력유형) + Bar(협력국 Top15) + H-Bar(기관 Top20) |
| `sec7_5` | 학술지 분석 | H-Bar(학술지 Top30) + Bar(JIF분포) + Line(Q1비율 추이) |

### 섹션 8: IBS 유발논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec8_1` | 유발논문 현황 | Stacked Bar(연도별) + Line(한국 비중) |
| `sec8_2` | 인프라별 분석 | Doughnut(비율) + Stacked Bar(연도 추이) + 테이블 |
| `sec8_3` | 수혜기관 분석 | Doughnut(기관유형) + H-Bar(기관 Top30) |
| `sec8_4` | 분야별 분석 | H-Bar(22분야) + Radar(RCA 상위12) |
| `sec8_5` | 영향력 분석 | Line(유발 vs 한국 평균TC) + Bar(HCP) |
| `sec8_6` | 협력 네트워크 | Doughnut(협력유형) + Bar(협력국 Top15) |

### 섹션 9: KISTI vs IBS 비교

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec9_1` | 직접 논문 비교 | Grouped Bar(연도별) + 비교 테이블 |
| `sec9_2` | 유발논문 비교 | Grouped Bar(연도별) + 비교 테이블 |
| `sec9_3` | 종합 비교 | Grouped Bar(지표) + Stacked Bar(연도별) + 비교 테이블 |

*Note: sec9에는 인력 생산성 분석(sec6_4 대응)이 없음. IBS는 NST(국가과학기술연구회) 소관 출연연이 아니므로 인력 CSV 데이터 미보유.*

### 섹션 10: PAL 유발논문분석

| ID | 메뉴 | 차트 |
|----|------|------|
| `sec10_1` | 유발논문 현황 | Stacked Bar(연도별) + Line(한국 비중) |
| `sec10_2` | 인프라별 분석 | Doughnut(비율) + Stacked Bar(연도 추이) + 테이블 |
| `sec10_3` | 수혜기관 분석 | Doughnut(기관유형) + H-Bar(기관 Top30) |
| `sec10_4` | 분야별 분석 | H-Bar(22분야) + Radar(RCA 상위12) |
| `sec10_5` | 영향력 분석 | Line(유발 vs 한국 평균TC) + Bar(HCP) |
| `sec10_6` | 협력 네트워크 | Doughnut(협력유형) + Bar(협력국 Top15) |

*Note: PAL(포항가속기연구소)은 WoS에서 POSTECH 하위기관으로 분류되어 org_alias 단독 분리가 불가능. 유발논문(사사표기 기반)만 분석.*

---

## 인프라 분류 키워드

| 인프라 | 키워드 |
|--------|--------|
| KSC/NURION | `KSC-`, `NURION` (슈퍼컴퓨터) |
| KREONET | `KREONET` (연구망) |
| EDISON | `EDISON` (e-Science 플랫폼) |
| PLSI/KIAF | `PLSI`, `KIAF` (이전 슈퍼컴) |
| 기타 KISTI 지원 | 위 키워드 없이 `KISTI`만 매칭 |

---

## 현재 데이터 기준 통계 (2024년 데이터)

| 항목 | KISTI | KBSI | IBS | PAL |
|------|-------|------|-----|-----|
| 직접 논문 (사사 제외) | 1,956건 | 4,487건 | 2,606건 | N/A |
| 유발논문 (사사표기 기반) | 6,104건 | 7,810건 | 8,290건 | 3,123건 |
| 중복(소속+사사) → 유발로 이동 | 624건 | 2,345건 | 6,617건 | N/A |
| 평균 피인용 (직접) | 53.0회 | 25.0회 | 24.5회 | N/A |
| 평균 피인용 (유발) | 30.9회 | 22.9회 | — | 30.5회 |
| 총현원 (2021) | 512명 | 392명 | N/A (비NST) | N/A |
| 박사인력 (2021) | 257명 | 181명 | N/A (비NST) | N/A |

| 항목 | 값 |
|------|-----|
| 한국 전체 논문 | 955,146건 |
| KISTI 합산 한국 비중 | 0.84% |
| 평균 JIF (KISTI) | 4.36 |
| MNCS (유발논문) | 1.957 (한국 평균 대비 95.7% 높은 피인용 영향력) |
| 논문/10억원/년 (KISTI 유발) | 9.43 |
| 피인용/10억원/년 (KISTI 유발) | 291.44 |

---

## 소스 데이터 출처 및 수집 방법

> **참고**: pickle 파일(`*.pkl`)은 원본 소스 데이터가 아니라, `preprocess_wos.py` 등이 원본(WoS TXT, JCR Excel 등)을 파싱하여 생성한 **중간 생성물**이다. 원본 소스 데이터는 `KISTEP/rawdata/`에 보관.

| 데이터 | 출처 | 수집 방법 | 기준년도 | 핵심 내용 |
|--------|------|-----------|----------|-----------|
| WoS 논문 (`wos_data.pkl`) | Clarivate Web of Science SCIE | WoS 검색 → TXT 다운로드(`rawdata/wos/`) → `preprocess_wos.py` 변환 | 2008-2024 | 한국 SCIE 논문 964,378건 (UT, PY, TC, SO, DT, SN, EI 등) |
| WoS 기관 (`wos_institutions.pkl`) | Clarivate Web of Science | 동일 TXT에서 C1/RP 필드 파싱 | 2008-2024 | 기관별 매핑 2,813,616건 (org_alias, institution_type_7, country_code) |
| JCR JIF (`jcr_jif.pkl`) | Clarivate JCR (Journal Citation Reports) | JCR 엑셀(`rawdata/jcr/`) 다운로드 → pickle 변환 | 2008-2023 | 저널별 JIF, JIF Quartile (Q1-Q4) |
| ESI 분야 (`esi_journal_map.pkl`) | Clarivate ESI (Essential Science Indicators) | ESI 저널 분류표(`rawdata/esi/`) 다운로드 | 2024 기준 | ISSN → ESI 22개 연구분야 매핑 |
| KISTI 유발논문 (`kisti_induced_papers.json`) | WoS FU/FX 필드 키워드 검색 | KISTI 인프라 키워드(KSC, NURION, KREONET, EDISON 등) 매칭 | 2008-2024 | 6,307건 (인프라 유형별 분류 포함) |
| KBSI 유발논문 (`kbsi_induced_papers.json`) | WoS FU/FX 필드 키워드 검색 | `scan_kbsi_induced.py`로 KBSI 키워드 매칭 | 2008-2024 | KBSI 인프라 활용 논문 |
| IBS 유발논문 (`ibs_induced_papers.json`) | WoS FU/FX 필드 키워드 검색 | `scan_ibs_induced.py`로 IBS 키워드(`\bIBS\b`, `Institute for Basic Science`) 매칭 | 2008-2024 | 8,294건 (IBS 연구센터 지원 논문) |
| PAL 유발논문 (`pal_induced_papers.json`) | WoS FU/FX 필드 키워드 검색 | `scan_pal_induced.py`로 PAL 키워드(`Pohang Accelerat`, `Pohang Light Source`, `PAL-XFEL`, `PLS-II`) 매칭 | 2008-2024 | 3,123건 (포항가속기연구소 활용 논문) |
| 출연연 인력 CSV | 국가과학기술연구회(NST) 공시자료 | 수기 수집 (CP949 CSV) | 2021.12.31 기준 | 25개 출연연 학위별 정규인력 (박사/석사/학사이하/총현원) |
| 경제적 가치 참고수치 | KISTEP, KREONET 보고서 | 웹 조사 (2026.02 수집) | 2022 기준 | 논문당 연구비, 인프라 예산, B/C 비율 |
| 국제 비교 참고수치 | XSEDE/PRACE/NERSC 등 공식 보고서·논문 | 웹 조사 (2026.02 수집) | 2011-2023 | 논문수, 예산, ROI, 피인용 영향력 |
| 한국 연도×분야별 평균TC | WoS 논문 데이터 자체 계산 | `compute_korea_stats()` → `kr_avg_tc_by_year_field` | 2008-2024 | MNCS 분모용. 연도·ESI 22분야별 한국 평균TC |

### sec2_7 경제적 가치 추정 — 참고 데이터 상세

| 참고 수치 | 값 | 출처 | 기준년도 |
|-----------|-----|------|----------|
| 논문당 연구비 (학술연구) | 1.3억원/편 | KISTEP 국가연구개발사업 성과분석 보고서 | 2022 |
| 논문당 연구비 (출연연 직접비) | 5.0억원/편 | NST/KISTEP 출연연 R&D 효율성 자료에서 추정 | 2022 |
| KREONET 연간 예산 | ~81억원/년 | KREONET 경제적 효과분석 (ScienceON) | 2020-2023 평균 |
| KSC 슈퍼컴 연간 예산 | ~300억원/년 | 6호기 총사업비 4,483억원 ÷ 15년 추정 | 2024 |
| KREONET B/C 비율 | 13~21배 | KREONET 경제적 효과분석 (ScienceON) | 2020-2023 |
| KISTI 인프라 연간 예산 | ~381억원/년 | KSC + KREONET 합산 | 2024 |

### sec2_7 객관적 분석 지표 — MNCS & 예산 정규화

| 지표 | 설명 | KISTI 유발논문 값 |
|------|------|-------------------|
| **MNCS** (피인용 영향력 지수) | 각 논문의 피인용수를 "같은 분야·같은 연도의 한국 평균 피인용수"로 나눈 뒤 평균. 1.0 = 한국 평균, 1.957 = 평균보다 95.7% 높은 인용. InCites CNCI, SciVal FWCI와 동일 원리 | **1.957** (6,044편 매칭) |
| **논문/10억원/년** | 연간 유발논문 수 ÷ 연간 인프라 예산(10억원) | **9.43** |
| **피인용/10억원/년** | 연간 총 피인용수 ÷ 연간 인프라 예산(10억원) | **291.44** |
| `kr_avg_tc_by_year_field` | MNCS 분모 — 한국 전체 논문의 연도×ESI분야별 평균TC | `compute_korea_stats()` 7번째 반환값 |

### sec2_8 국제 비교 — 참고 데이터 상세

| 프로그램 | 출처 | 기준년도 |
|----------|------|----------|
| XSEDE | Stewart et al. (2023) *Scientometrics* 128, 1769-1798; Wang & von Laszewski (2021) PEARC '21; HPCwire (2022.7) | 2011-2022 |
| PRACE | PRACE 공식통계, ERF-AISBL, InsideHPC | 2010-2023 |
| NERSC | NERSC 공식 웹사이트, LBNL 발표자료 | 상시 |
| HECToR/ARCHER | Story of HECToR (archer.ac.uk) | 2008-2014 |

#### sec2_8 기간 매칭 비교 (Overlap Period Comparison)

프로그램 간 운영기간이 다르므로, **겹치는 기간만 추출**하여 KISTI 유발논문을 재계산.

| 비교 대상 | 겹치는 기간 | KISTI 논문 | 상대 논문 | KISTI MNCS |
|-----------|------------|-----------|----------|-----------|
| XSEDE | 2011-2022 (12년) | 5,449 | 20,000 | 1.975 |
| PRACE | 2010-2023 (14년) | 5,953 | 미공개 | 1.987 |
| HECToR | 2008-2014 (7년) | 38 | 800 | 1.365 |

*주: HECToR 비교는 2008-2018 SCIE 원시 데이터 부재로 KISTI 측 집계 극히 불완전. 참고용으로만 활용.*
*주: KISTI 예산 381억원/년 고정, XSEDE 315억원/년 기준. 환율 1 USD = 1,350 KRW.*

---

## 제약사항

1. **연구자 분석 보류**: `wos_data.pkl`에 AU/AF 필드 없음. 향후 `preprocess_wos.py`에 AU 추가 후 구현 가능.
2. **유발논문 2008-2018 SCIE 부재**: 해당 기간 SCIE 원시 TXT 파일 없어 유발논문 과소 집계. 대시보드에 주석 표시.
3. **메모리**: `compute.py` 실행 시 ~3-4GB RAM 필요 (pickle 로딩). 실행 후 JSON 저장하고 종료.
4. **Multidisciplinary 재분류**: CR 데이터 부재로 미적용. 2026년 데이터 수집 시 CR 포함 시 적용 가능.
5. **MNCS 한계**: MNCS 분모가 한국 전체 평균TC(global 평균이 아님). 국제 표준 CNCI/FWCI는 글로벌 평균 기준이지만 현재 글로벌 데이터 미보유. 대시보드에 한계 명시.
6. **국제 비교 정합성**: 프로그램 간 예산 범위·기간·논문 집계 방법 상이. 기간 매칭 비교(overlap period)로 기간 불일치 보정, 10억원당 정규화로 규모 차이 보정. 2008-2018 SCIE 데이터 부재 구간은 `caveat` 경고 자동 부여. 대시보드에 한계 박스 표시.
7. **C1 필드 국가명 파싱**: WoS C1 필드에서 국가명 추출 시 `", "` 분리 후 마지막 토큰 사용. 대형 공동연구(CDF, CMS 등)에서 저자 이니셜(예: `"Hou, S."` → `"S"`)이 국가로 오인되는 버그가 있었음. `len(country) >= 4` 필터로 해결 (WoS 최단 국가명: IRAN, PERU, CUBA, OMAN = 4자). sec1_4, sec2_6, sec4_4, sec5_6, sec7_4, sec8_6 6곳에 적용.
8. **IBS 인력 생산성 제외**: IBS는 NST(국가과학기술연구회) 소관 출연연이 아니므로 인력 CSV에 포함되지 않음. sec9에는 인력 생산성 분석(sec6_4 대응)이 없음.
9. **PAL 직접논문 분리 불가**: PAL(포항가속기연구소)은 WoS에서 POSTECH 하위기관으로 분류(`org_alias = "POSTECH"`)되어 직접논문 분리가 불가능. 유발논문(사사표기 기반)만 분석. `\bPAL\b` 단독 키워드는 오탐률이 높아 사용하지 않음.

---

## 라이브차트 HTML 생성

`/api/export-html` POST 엔드포인트로 서버·인터넷 없이 브라우저만으로 동작하는 독립 HTML 파일 생성.

**흐름**: dashboard.html 원문 읽기 → CDN JS 인라인 삽입 → data_cache + exclusions 인라인 주입 → 서버 의존 UI 제거 → 독립 부팅 코드 치환 → `generated/html/` 저장

**기간 제한**: 생성 시 지정한 기간(start_year~end_year)으로 `PERIOD` 초기화 + `recomputeAllStats()` 호출. 입력란은 해당 범위 밖 값 입력 불가 (키보드 차단, 스피너 min/max 제한).

**저장 위치**: `generated/html/dashboard_v{version}_{start}-{end}.html` (~23MB)

---

## 기술 스택

- **Backend**: Python 3, Flask (port 5002)
- **Frontend**: 단일 HTML, Chart.js 4.4.7, chartjs-plugin-datalabels 2.2.0
- **UI**: 사이드바 메뉴 접힘/펼침 (섹션 번호 클릭, 초기 모두 접힘)
- **테마**: 다크 테마 (KISTEP 대시보드와 동일 CSS 변수)
- **데이터**: KISTEP 프로젝트의 pickle 중간 생성물 의존 (원본: `KISTEP/rawdata/`, 생성물: `KISTEP/generated/`)
- **라이브차트**: CDN JS + data_cache를 인라인 삽입한 자체 완결형 HTML (서버 불필요)
