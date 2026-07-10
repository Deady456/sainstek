from .upload import get_service, _token_path


def main():
    token_path = _token_path()
    print(f"Authorizing for channel token: {token_path.name}")
    print("Opening browser for Google authorization...")
    print("Pastikan kamu pilih channel yang benar di browser!")
    yt = get_service()
    resp = yt.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if items:
        ch = items[0]["snippet"]["title"]
        print(f"Authorized OK. Channel: {ch}")
        print(f"Token saved: {token_path.name}")
        print("Uploads akan pake channel ini sampai channel di config.yaml diganti.")
    else:
        print("Authorized, but no YouTube channel is attached to this Google account.")
        print("Create a channel at youtube.com first, then re-run.")


if __name__ == "__main__":
    main()
