"""Serve the built React app from the backend, so a single `uvicorn` command runs everything.

Files in the build folder are served as they are; any other path that isn't under
/api gets index.html, so the app's own routes (/logs) work on reload. If the
app hasn't been built yet, / shows a short page explaining how.
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

log = logging.getLogger(__name__)

NOT_BUILT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vehicle Tracker</title>
<style>
  body{font-family:system-ui,sans-serif;background:#f8fafc;color:#0f172a;
       display:grid;place-items:center;min-height:100vh;margin:0}
  main{max-width:34rem;padding:2rem;background:#fff;border-radius:16px;
       box-shadow:0 1px 3px #0001;border:1px solid #e2e8f0}
  code{display:block;background:#0f172a;color:#e2e8f0;padding:.75rem 1rem;
       border-radius:10px;margin:.75rem 0;font-size:.9rem}
  a{color:#4f46e5}
</style></head>
<body><main>
  <h1>The backend is running</h1>
  <p>The web app just hasn't been built yet. Build it once (needs Node 20), then reload this page:</p>
  <code>cd frontend<br>npm install<br>npm run build</code>
  <p>The API works already: <a href="/api/health">/api/health</a>, <a href="/docs">/docs</a>.</p>
</main></body></html>"""


def mount_frontend(app: FastAPI, build_dir: Path | None):
    build_dir = build_dir.resolve() if build_dir else None
    index = build_dir / "index.html" if build_dir else None

    if index and index.exists():
        log.info("Serving the web app from %s", build_dir)
    elif build_dir:
        log.warning("Web app not built (%s missing); run `npm run build` in frontend/ to serve it here", index)

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/") or not build_dir:
            raise HTTPException(404, "Not found")
        if not index.exists():
            return HTMLResponse(NOT_BUILT, status_code=503)

        file = (build_dir / path).resolve()
        if path and file.is_file() and build_dir in file.parents:
            # hashed bundles never change; everything else is checked again each time
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(file, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
