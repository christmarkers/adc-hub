"""
sync_and_analyze.py
Google Drive의 학회별 폴더를 스캔하고,
새 포스터를 Claude AI로 분석해서 public/data.json에 저장합니다.
"""

import os
import json
import base64
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# ── 설정 ──────────────────────────────────────────────────────────────────────
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
DATA_PATH = Path('public/data.json')
ALREADY_ANALYZED_PATH = Path('public/analyzed_ids.json')

# ── Google Drive 초기화 ────────────────────────────────────────────────────────
def get_drive_service():
    sa_json = os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']
    sa_info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

# ── Drive 폴더 스캔 ───────────────────────────────────────────────────────────
def list_conference_folders(service, root_folder_id):
    """루트 폴더 하위의 학회명 폴더 목록 반환"""
    result = service.files().list(
        q=f"'{root_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields='files(id, name)',
        orderBy='name'
    ).execute()
    return result.get('files', [])

def list_posters_in_folder(service, folder_id):
    """폴더 내 PDF/이미지 파일 목록 반환"""
    q = f"'{folder_id}' in parents and trashed=false and (mimeType='application/pdf' or mimeType contains 'image/')"
    result = service.files().list(
        q=q,
        fields='files(id, name, mimeType, createdTime)',
        orderBy='createdTime desc'
    ).execute()
    return result.get('files', [])

def download_file(service, file_id, mime_type):
    """파일을 바이트로 다운로드"""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()

# ── Claude AI 분석 ────────────────────────────────────────────────────────────
ANALYSIS_PROMPT = """이 ADC(Antibody-Drug Conjugate) 관련 학회 포스터를 분석해서 아래 JSON 형식으로만 응답해줘.
마크다운 코드블록 없이 순수 JSON만 출력해.

{
  "title": "포스터 제목 (약물명 + 연구명 포함)",
  "company": "개발사명",
  "target": "타겟 항원 (예: HER2, TROP2, HER3)",
  "indication": "적응증 (예: HER2+ Metastatic Breast Cancer)",
  "payload": "Payload 물질명",
  "linker": "Linker 종류",
  "dar": "DAR 수치",
  "phase": "임상 단계 (예: Phase 1, Phase 2, Phase 3, Approved, Preclinical)",
  "orr": "ORR 수치 (없으면 N/A)",
  "pfs": "PFS 수치 (없으면 N/A)",
  "os": "OS 수치 (없으면 N/A)",
  "dlt": "주요 DLT 또는 AE (없으면 N/A)",
  "highlight": "150자 이내 핵심 인사이트 요약 (한국어로)"
}

포스터에서 명확하지 않은 항목은 반드시 "N/A"로 표기해줘."""

def analyze_poster(client, file_bytes, mime_type, conf_name, file_name):
    """Claude API로 포스터 분석"""
    b64 = base64.standard_b64encode(file_bytes).decode('utf-8')

    if mime_type == 'application/pdf':
        file_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64}
        }
    else:
        file_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": b64}
        }

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                file_block,
                {"type": "text", "text": ANALYSIS_PROMPT}
            ]
        }]
    )

    raw = message.content[0].text.strip()
    raw = raw.replace('```json', '').replace('```', '').strip()
    result = json.loads(raw)
    result['conf'] = conf_name
    result['file_name'] = file_name
    result['analyzed_at'] = datetime.now(timezone.utc).isoformat()
    return result

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    print("=== ADC Poster Sync & Analyze ===")

    # 기존 데이터 로드
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing_data = json.loads(DATA_PATH.read_text()) if DATA_PATH.exists() else {"posters": [], "updated_at": ""}
    existing_posters = existing_data.get("posters", [])

    # 이미 분석된 파일 ID 목록
    analyzed_ids = set()
    if ALREADY_ANALYZED_PATH.exists():
        analyzed_ids = set(json.loads(ALREADY_ANALYZED_PATH.read_text()))

    # 클라이언트 초기화
    drive = get_drive_service()
    claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    root_folder_id = os.environ['DRIVE_FOLDER_ID']

    # 학회 폴더 스캔
    conf_folders = list_conference_folders(drive, root_folder_id)
    print(f"발견된 학회 폴더: {len(conf_folders)}개")

    new_count = 0
    new_posters = []

    for folder in conf_folders:
        conf_name = folder['name']
        print(f"\n[{conf_name}] 스캔 중...")

        posters = list_posters_in_folder(drive, folder['id'])
        for poster in posters:
            file_id = poster['id']
            file_name = poster['name']
            mime_type = poster['mimeType']

            if file_id in analyzed_ids:
                print(f"  SKIP (이미 분석됨): {file_name}")
                continue

            print(f"  분석 중: {file_name}")
            try:
                file_bytes = download_file(drive, file_id, mime_type)
                result = analyze_poster(claude, file_bytes, mime_type, conf_name, file_name)
                result['drive_file_id'] = file_id
                result['id'] = file_id
                new_posters.append(result)
                analyzed_ids.add(file_id)
                new_count += 1
                print(f"  완료: {result.get('title', file_name)}")
            except Exception as e:
                print(f"  오류 ({file_name}): {e}")
                continue

    # 데이터 병합 및 저장
    all_posters = new_posters + existing_posters
    output = {
        "posters": all_posters,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_posters)
    }
    DATA_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    ALREADY_ANALYZED_PATH.write_text(json.dumps(list(analyzed_ids), ensure_ascii=False))

    print(f"\n=== 완료: 신규 {new_count}개 분석, 총 {len(all_posters)}개 포스터 ===")

if __name__ == '__main__':
    main()
