import json, os, time
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from openai import OpenAI
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, CONFIG, ROOT

SCOPES = ["https://www.googleapis.com/auth/blogger"]
CLIENT_SECRET = ROOT / "client_secret.json"
BLOG_ID = os.environ.get("BLOG_ID", "")


def _token_path() -> Path:
    return ROOT / "token_blogger.json"


def _get_service():
    token_path = _token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("blogger", "v3", credentials=creds)


def _call_llm(api_key: str, base_url: str, model: str, user_msg: str) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.choices[0].message.content

def expand_article(script_data: dict) -> dict:
    full_text = script_data.get("full_text", "")

    user_msg = (
        f"Teks video pendek berikut:\n\n{full_text}\n\n"
        f"Niche: {CONFIG['niche']}\n"
        f"Tulis artikel blog 500-700 kata dalam bahasa Indonesia berdasarkan teks di atas. "
        f"Kembangkan dengan penjelasan tambahan yang relevan, fakta pendukung, dan kesimpulan. "
        f"Gunakan format HTML paragraf (<p>). Beri judul artikel yang engaging (>40 karakter). "
        f"Jangan tambahkan informasi palsu. Kembalikan ONLY valid JSON: "
        f"{{\"title\": \"...\", \"content\": \"<p>...</p>\"}}"
    )

    try:
        raw = _call_llm(LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, user_msg)
    except Exception as e:
        if "429" in str(e) or "insufficient_quota" in str(e):
            fallback_key = os.environ.get("GROQ_API_KEY_2", "")
            if fallback_key:
                print("    Groq rate limited, using fallback key...")
                raw = _call_llm(fallback_key, LLM_BASE_URL, LLM_MODEL, user_msg)
            else:
                raise
        else:
            raise

    article = json.loads(raw)
    tags = script_data.get("tags", [])
    article["tags"] = tags[:5]
    article["video_id"] = script_data.get("video_id", "")
    return article


def post(article: dict) -> str | None:
    if not BLOG_ID:
        print("    BLOG_ID not set, skipping")
        return None

    service = _get_service()

    content = article["content"]
    if article.get("video_id"):
        yt_embed = (
            '<div style="text-align:center;margin:20px 0;">'
            '<iframe width="560" height="315" '
            f'src="https://www.youtube.com/embed/{article["video_id"]}" '
            'frameborder="0" allowfullscreen></iframe></div>'
        )
        content = yt_embed + content

    vid = article.get("video_id", "")
    labels = article.get("tags", [])[:5]
    if vid:
        labels.append("vid_" + vid)

    body = {
        "kind": "blogger#post",
        "title": article["title"],
        "content": content,
        "labels": labels,
    }

    for attempt in range(3):
        try:
            result = service.posts().insert(blogId=BLOG_ID, body=body).execute()
            url = result.get("url", "")
            print(f"    blog post published: {url}")
            return url
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"    blog post failed: {e}")
    return None


def publish(script_data: dict) -> str | None:
    vid = script_data.get("video_id", "")
    if vid:
        try:
            service = _get_service()
            existing = service.posts().list(blogId=BLOG_ID, labels=f"vid_{vid}", maxResults=1).execute()
            if existing.get("items"):
                url = existing["items"][0].get("url", "")
                print(f"  Already posted: {url}")
                return url
        except Exception:
            pass
    print("  Expanding script to blog article...")
    article = expand_article(script_data)
    print(f"    title: {article['title']}")
    return post(article)
