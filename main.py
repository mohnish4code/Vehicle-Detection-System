"""Run the whole app (API + web page) from the project folder with one command.

    uvicorn main:app --reload      then open http://127.0.0.1:8000
    python main.py                 same, and opens the browser for you

The web page is the built React app in frontend/dist (build it once with
`npm install` and `npm run build` in frontend/). For working on the frontend
itself, `npm run dev` in frontend/ still gives hot reload on port 5173.
"""

import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.api.main import app  # noqa: E402

__all__ = ["app"]

HOST, PORT = "127.0.0.1", 8000


def open_when_ready(url: str, timeout: float = 180):
    """Open the browser once the server answers (loading the models takes a few seconds)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{url}api/health", timeout=2)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(1)


if __name__ == "__main__":
    import uvicorn

    url = f"http://{HOST}:{PORT}/"
    print(f"\n  Vehicle Tracker starting at {url}  (Ctrl+C to stop)\n", flush=True)
    threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True,
                reload_dirs=[str(BACKEND)], reload_includes=["*.py", "*.toml"])
