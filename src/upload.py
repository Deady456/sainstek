from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as gbuild
from googleapiclient.http import MediaFileUpload
from .config import ROOT, CONFIG

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CLIENT_SECRET = ROOT / "client_secret.json"


def _token_path() -> Path:
    channel = CONFIG.get("upload", {}).get("channel", "default")
    return ROOT / f"token_{channel}.json"


def get_service():
    token_path = _token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), None)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return gbuild("youtube", "v3", credentials=creds)


def upload_video(video_path: Path, title: str, description: str, tags: list[str],
                 publish_at: str | None = None) -> str:
    yt = get_service()
    up = CONFIG["upload"]
    all_tags = list({*tags, *up["default_tags"]})

    status = {"selfDeclaredMadeForKids": up["made_for_kids"]}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = up["privacy"]

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": all_tags,
            "categoryId": up["category_id"],
        },
        "status": status,
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
        
    video_id = resp["id"]
    try:
        import subprocess
        thumb_path = video_path.with_name("thumb_auto.jpg")
        subprocess.run([
            "ffmpeg", "-y", "-ss", "1.0", "-i", str(video_path),
            "-vframes", "1", "-q:v", "2", str(thumb_path)
        ], capture_output=True)
        if thumb_path.exists():
            thumb_media = MediaFileUpload(str(thumb_path), mimetype="image/jpeg")
            yt.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
    except Exception as e:
        print(f"    [Warn] Gagal mengupload custom thumbnail: {e}")
        
    return video_id


def delete_video(video_id: str):
    yt = get_service()
    yt.videos().delete(id=video_id).execute()
