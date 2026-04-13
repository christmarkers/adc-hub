# ADC Poster Hub — 세팅 가이드

Google Drive에 포스터를 추가하면 자동으로 AI 분석 후 웹페이지에 반영되는 시스템입니다.

---

## 전체 구조

```
Google Drive (관리자만)
  📁 ADC Posters/          ← DRIVE_FOLDER_ID 이 폴더
    📁 ASCO 2025/
      📄 poster1.pdf
    📁 ESMO 2025/
      📄 poster2.pdf
          ↓ 1시간마다 자동 감지
GitHub Actions
  → Claude AI 분석 → data.json 업데이트
          ↓
GitHub Pages (팀원 접속)
  https://{username}.github.io/adc-hub/
```

---

## Step 1. GitHub 저장소 생성

1. github.com → New repository
2. 이름: `adc-hub`
3. **Public** 선택 (GitHub Pages 무료 사용)
4. 아래 파일들을 저장소에 업로드:
   - `adc_poster_hub.html` → `public/index.html` 로 이름 변경해서 업로드
   - `public/data.json`
   - `scripts/sync_and_analyze.py`
   - `.github/workflows/sync.yml`

---

## Step 2. GitHub Pages 활성화

1. 저장소 → Settings → Pages
2. Source: **GitHub Actions** 선택
3. 아래 `pages.yml` 파일을 `.github/workflows/` 에 추가:

```yaml
name: Deploy to GitHub Pages
on:
  push:
    branches: [main]
  workflow_run:
    workflows: ["Sync Google Drive & Analyze Posters"]
    types: [completed]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: public/
      - uses: actions/deploy-pages@v4
        id: deployment
```

---

## Step 3. Google Drive API 설정 (15분)

### 3-1. Google Cloud 프로젝트 생성
1. console.cloud.google.com 접속
2. 새 프로젝트 생성 (이름: `adc-hub`)
3. APIs & Services → Enable APIs → **Google Drive API** 활성화

### 3-2. 서비스 계정 생성
1. APIs & Services → Credentials → Create Credentials → **Service Account**
2. 이름: `adc-hub-service`
3. 생성 후 → Keys 탭 → Add Key → **JSON** 다운로드
4. 다운로드된 JSON 파일 내용 전체를 복사해둠

### 3-3. Google Drive 폴더 공유
1. Google Drive에서 `ADC Posters` 폴더 생성
2. 폴더 우클릭 → 공유 → 서비스 계정 이메일 추가 (JSON 파일 안의 `client_email` 값)
3. 권한: **뷰어(Viewer)** 로 설정
4. 폴더 URL에서 ID 복사:
   `https://drive.google.com/drive/folders/[이 부분이 FOLDER_ID]`

---

## Step 4. GitHub Secrets 등록

저장소 → Settings → Secrets and variables → Actions → **New repository secret**

| Secret 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 3-2에서 다운로드한 JSON 파일 **전체 내용** |
| `DRIVE_FOLDER_ID` | 3-3에서 복사한 폴더 ID |

---

## Step 5. 첫 실행 테스트

1. 저장소 → Actions → "Sync Google Drive & Analyze Posters"
2. **Run workflow** 버튼 클릭 (수동 실행)
3. 로그 확인 → 완료 후 웹사이트 접속

---

## 이후 사용법

Google Drive의 `ADC Posters` 폴더에 학회명으로 하위 폴더를 만들고 PDF를 넣으면,
**최대 1시간 내**에 자동으로 AI 분석 후 웹페이지에 반영됩니다.

```
📁 ADC Posters/
  📁 ASCO 2025/        ← 폴더명이 학회명으로 자동 태깅
    📄 abstract_001.pdf
    📄 abstract_002.pdf
  📁 ESMO 2025/
    📄 poster_her2.pdf
```

### 즉시 반영하고 싶을 때
GitHub Actions → Run workflow 버튼 클릭 → 5~10분 내 반영

---

## 비용 안내

| 항목 | 비용 |
|---|---|
| GitHub Pages | 무료 |
| GitHub Actions | 무료 (월 2,000분) |
| Google Drive API | 무료 |
| Anthropic API | 포스터 1개당 약 $0.01~0.03 |

포스터 100개 분석해도 API 비용은 약 $1~3 수준입니다.
