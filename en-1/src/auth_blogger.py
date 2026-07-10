"""Run once locally to authorize Blogger access."""
from .blogger import _get_service

def main():
    print("Authorizing Blogger access...")
    svc = _get_service()
    blogs = svc.blogs().listByUser(userId="self").execute()
    for b in blogs.get("items", []):
        print(f"  Blog: {b['name']} (ID: {b['id']})")
    print("OK. Token saved to token_blogger.json")

if __name__ == "__main__":
    main()
