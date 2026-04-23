# KISTI Policy 대시보드 — 운영 및 배포 가이드

> 작성일: 2026-04-23
> 대상: Google Cloud Platform 이전 + 연간 데이터 갱신 사이클 운영

---

## 1. 배경

- `KISTI_Policy/`는 `KISTEP/` 본과제의 파생 분석 도구로, 동일한 WoS pickle 데이터를 공유한다.
- 매년 신규 WoS 원시 데이터가 수집되면 pickle → `data_cache.json`을 재생성해야 한다.
- 이전 후에도 **매년 1회 갱신 사이클**이 반복되므로, 일회성 배포가 아니라 연간 운영 가능한 구조로 설계한다.

---

## 2. 파이프라인 구조

```
[원시 소스]                   [중간 생성물]                 [최종 출력]
KISTEP/rawdata/               KISTEP/generated/             KISTI_Policy/
├── wos/*.txt                  *.pkl (wos_data 931MB,        data_cache.json
├── jcr/*.xlsx                  wos_institutions 580MB 등)    (51MB)
├── esi/*.xlsx                        │                             │
└── institutions/*              (심볼릭 링크)                        │
         │                             │                             │
         ▼                             ▼                             ▼
preprocess_wos.py           scan_*_induced.py × 3        app.py (Flask, 5002)
                            compute.py                           │
                                                                 ▼
                                                         대시보드 (52 pages)
```

**핵심**: `app.py`는 `data_cache.json`과 `exclusions.json` **단 두 파일**만 필요하다. pickle은 `compute.py` 단계에서만 소요된다.

---

## 3. 연간 갱신 사이클 (매년 수행)

### 순서

| 단계 | 위치 | 명령 | 산출물 |
|------|------|------|--------|
| 1 | `KISTEP/rawdata/wos/` | 신규 WoS TXT 파일 수집 (수기) | 원본 TXT |
| 2 | `KISTEP/` | `python3 preprocess_wos.py` | `generated/YYYY/*.pkl` |
| 3 | `KISTEP/` | 심볼릭 링크 갱신 (최신 generated로) | `*.pkl` 심볼릭 링크 |
| 4 | `KISTI_Policy/` | `python3 scan_kbsi_induced.py` | `kbsi_induced_papers.json` |
| 5 | `KISTI_Policy/` | `python3 scan_ibs_induced.py` | `ibs_induced_papers.json` |
| 6 | `KISTI_Policy/` | `python3 scan_pal_induced.py` | `pal_induced_papers.json` |
| 7 | `KISTI_Policy/` | `python3 compute.py` | `data_cache.json` (~51MB) |
| 8 | 클라우드 | 배포 명령 (아래 섹션 5 참조) | 대시보드 갱신 |

### 전제조건

- 로컬 맥에 최소 RAM 4GB (compute.py 실행 시 3-4GB 사용)
- Python 패키지: `flask` (compute.py는 표준 라이브러리만 사용)
- KISTEP 루트에 pickle 심볼릭 링크 정상 연결

### 자동화 스크립트 (`rebuild.sh`)

```bash
#!/bin/bash
set -e

# 1. KISTEP pickle 재생성
cd /Users/kimsuntae/KISTEP
python3 preprocess_wos.py

# 2. 유발논문 스캔 3종
cd /Users/kimsuntae/KISTI_Policy
python3 scan_kbsi_induced.py
python3 scan_ibs_induced.py
python3 scan_pal_induced.py

# 3. 데이터 캐시 생성
python3 compute.py

# 4. 클라우드 배포 (Cloud Run 예시)
gcloud run deploy kisti-policy \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated
```

---

## 4. GCP 이전 전략 비교

### 전략 1: 로컬 처리 + 클라우드 서빙 ✅ **권장**

```
[로컬 맥]                              [GCP]
원시 수집 → pickle → data_cache.json ──▶ Cloud Run
                   (51MB 업로드)
```

- **장점**: 업로드 최소(51MB), 클라우드 비용 최소, WoS 라이선스 이슈 회피
- **단점**: 로컬 맥 필요 (최초 1회 연간 작업)
- **적합**: 연 1회 갱신 + 단일 운영자

### 전략 2: 전체 파이프라인 클라우드

```
[GCS: 원본] ──▶ [Cloud Run Jobs / GCE VM]
                preprocess → pickle → compute
                           ▼
                    Cloud Run (Flask)
```

- **장점**: 원본 데이터 공유·버전 관리, 협업 용이, 로컬 부담 ↓
- **단점**: 초기 셋업 복잡, WoS 라이선스 검토 필요, pickle 1.5GB 저장
- **비용**: 스토리지 월 ~$0.03, VM 실행 회당 ~$0.01 (무시 수준)

### 전략 3: 하이브리드

- pickle 생성: 로컬
- pickle 백업: GCS (버전 관리)
- `data_cache.json` 생성: 로컬 또는 Cloud Run Jobs
- 서빙: Cloud Run

---

## 5. GCP 배포 옵션

| 옵션 | 적합도 | 비고 |
|------|-------|------|
| **Cloud Run** | ⭐⭐⭐⭐⭐ | Flask 컨테이너화, 자동 HTTPS, 무료 티어 충분 |
| **App Engine Standard** | ⭐⭐⭐⭐ | `app.yaml` 간단. 파일 512MB 제한 (현재 51MB OK) |
| **Compute Engine (VM)** | ⭐⭐⭐ | compute.py까지 돌릴 때만 필요 |
| **GCS + Static** | ❌ | Flask 동적 라우트(`/api/*`) 때문에 불가 |

### Cloud Run 배포 준비물

#### 5.1 `requirements.txt`

```
flask==3.0.0
```

#### 5.2 `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py compute.py ./
COPY templates/ ./templates/
COPY data_cache.json exclusions.json ./
COPY generated/ ./generated/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
```

#### 5.3 `app.py` 수정 필요 사항

```python
# 현재
KISTEP_BASE = Path("/Users/kimsuntae/KISTEP")

# 변경 (환경변수 기반, 없으면 비활성)
KISTEP_BASE = Path(os.environ.get("KISTEP_BASE", ""))

# 포트 바인딩 (Cloud Run은 PORT 환경변수 강제)
port = int(os.environ.get("PORT", 5002))
app.run(host="0.0.0.0", port=port)
```

#### 5.4 `.gcloudignore`

```
KISTEP/
rawdata/
*.pkl
__pycache__/
.git/
```

### 배포 명령

```bash
# 최초 배포
gcloud run deploy kisti-policy \
  --source . \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 1Gi

# 이후 data_cache.json만 갱신 시
gcloud run deploy kisti-policy --source . --region asia-northeast3
```

---

## 6. 두 프로젝트 관계

| 프로젝트 | 역할 | 원본 의존 | 갱신 주기 |
|---------|------|----------|----------|
| `KISTEP/` | 한국 SCIE 전체 분석 (본과제) | WoS TXT, JCR, ESI | 연 1회 |
| `KISTI_Policy/` | 인프라 유발효과 분석 (파생) | KISTEP pickle 재사용 | 연 1회 (KISTEP 갱신 후) |

두 프로젝트의 pickle은 **심볼릭 링크로 공유**되므로 별도 복제 불필요.

---

## 7. 제약사항 및 주의점

### 7.1 WoS 라이선스
- Clarivate WoS TXT/pickle을 외부 클라우드에 저장하기 전 **계약 조건 확인 필수**
- 전략 1(로컬 처리)에서는 원본이 로컬에만 존재하므로 라이선스 리스크 없음

### 7.2 메모리
- `compute.py`: 3-4GB RAM 필요 (pickle 전체 로딩)
- Cloud Run에서 실행 시 메모리 플랜 2Gi 이상 필요
- App Engine Standard는 인스턴스 메모리 한도(512MB~2GB) 주의

### 7.3 데이터 크기
- `data_cache.json`: 51MB (Cloud Run 컨테이너 이미지에 포함 가능)
- pickle 총합: 1.5GB+ (컨테이너 포함 비권장, GCS 별도 저장)

### 7.4 갱신 후 검증
- 배포 전 로컬에서 `python3 app.py` 실행 → `http://localhost:5002` 접속하여 52 페이지 샘플 확인
- `exclusions.json`은 수동 편집 이력이 있으므로 덮어쓰지 않도록 주의

### 7.5 연도 필터
- 대시보드 기본 기간은 `compute.py`에서 설정. 신규 연도 데이터 추가 시 `PERIOD` 변수 확인
- 라이브차트 HTML 생성 기능(`/api/export-html`)은 기간 제한 기능 내장

---

## 8. 체크리스트 — 연간 갱신 시

- [ ] `KISTEP/rawdata/wos/`에 신규 TXT 추가
- [ ] `preprocess_wos.py` 실행 완료 (pickle 파일 크기·건수 확인)
- [ ] 심볼릭 링크가 최신 `generated/YYYY/`를 가리키는지 확인
- [ ] `scan_*_induced.py` 3종 실행 (JSON 건수 증가 확인)
- [ ] `compute.py` 실행 (에러 없이 완료 + `data_cache.json` 51MB 근처)
- [ ] 로컬 `app.py` 실행하여 대시보드 샘플 검증
- [ ] `exclusions.json` 백업 (배포 전)
- [ ] Cloud Run 배포
- [ ] 배포된 URL에서 52 페이지 중 샘플 3-4개 확인

---

## 9. 참고

- 프로젝트 개요: [CLAUDE.md](CLAUDE.md)
- 파일 설명: [파일목록_참고자료.txt](파일목록_참고자료.txt)
- Cloud Run 공식 문서: https://cloud.google.com/run/docs
