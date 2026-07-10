import socket
import requests
from .config import PEXELS_API_KEY

PEXELS_TEST_URL = "https://api.pexels.com/videos/search?query=test&orientation=portrait&per_page=1&size=medium"

def check_internet() -> bool:
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        return False

def check_pexels() -> bool:
    try:
        r = requests.get(PEXELS_TEST_URL, headers={"Authorization": PEXELS_API_KEY}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False

def main():
    ok = True

    print("  [health] checking internet...", end=" ")
    if check_internet():
        print("OK")
    else:
        print("FAIL (no internet)")
        ok = False

    print("  [health] checking Pexels API...", end=" ")
    if check_pexels():
        print("OK")
    else:
        print("FAIL (Pexels unreachable)")
        ok = False

    if ok:
        print("  [health] all checks passed, starting pipeline")
    else:
        print("  [health] prerequisites not met, skipping this run")

    return 0 if ok else 1

if __name__ == "__main__":
    exit(main())
