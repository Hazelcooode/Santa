"""Deploy the Sola WEBSITE from the newest `current_world` code on Modal.

Separate from the mobile deployment (modal_app.py): its own app, data volume and
secret, so the two never share data or affect each other. Run from this folder,
pointing SOLA_WEB_SRC at a checkout of current_world:

    git fetch origin current_world
    git worktree add ../Santa-web origin/current_world      # once; later: git -C ../Santa-web checkout --detach origin/current_world
    python3 -m modal secret create sola-web-secrets EXA_API_KEY=... CLOUDINARY_URL=... ANTHROPIC_API_KEY=...
    SOLA_WEB_SRC=../Santa-web python3 -m modal deploy modal_web.py

Modal prints https://<workspace>--sola-web-web.modal.run (website at /, people
create accounts at /register). The mobile app paths (/mobile) are not served here.
"""
import os
import base64
import threading
import time
from pathlib import Path

import modal

SRC = Path(os.environ.get("SOLA_WEB_SRC", Path(__file__).parent / ".." / "Santa-web")).resolve()
APP = "/app"
REBRAND = (
    "import pathlib,re\n"
    "n=0\n"
    "for d in ('/app/backend/app','/app/src'):\n"
    "    for f in pathlib.Path(d).rglob('*'):\n"
    "        if f.suffix in ('.py','.js','.css','.html') and f.is_file():\n"
    "            t=f.read_text(encoding='utf-8'); u=re.sub(r'\\bTaimi\\b','Sola',t)\n"
    "            if u!=t: f.write_text(u,encoding='utf-8'); n+=1\n"
    "p=pathlib.Path('/app/index.html'); p.write_text(re.sub(r'\\bTaimi\\b','Sola',p.read_text(encoding='utf-8')),encoding='utf-8')\n"
    "print('rebranded',n,'files')\n"
)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(SRC / "backend" / "requirements.txt"))
    .env({
        "APP_ENV": "production",          # current_world: live data, secure cookies, no seeded demo account
        "DATA_MODE": "live",
        "SEED_DEMO_ACCOUNT": "0",
        "COOKIE_SECURE": "1",
        "ALLOWED_HOSTS": "*.modal.run",
        "TAIMI_DB": "/data/sola-web.sqlite3",
        "CLOUDINARY_FOLDER": "sola-web",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    # copy=True so the rebrand step below can edit the files inside the image
    .add_local_dir(str(SRC / "backend" / "app"), f"{APP}/backend/app", copy=True, ignore=["**/__pycache__", "static/vendor/**"])
    .add_local_dir(str(SRC / "src"), f"{APP}/src", copy=True)
    .add_local_dir(str(SRC / "mobile"), f"{APP}/mobile", copy=True)   # present only because the backend mounts it; blocked below
    .add_local_file(str(SRC / "index.html"), f"{APP}/index.html", copy=True)
    # current_world still says "Taimi"; the app is called Sola (renamed on hazel). Replace the
    # whole word only, so code identifiers such as TaimiLaundryUI or taimi-bridge.js keep working.
    # Each build command becomes one Dockerfile line, so the script travels base64-encoded on one line.
    .run_commands('python -c "import base64; exec(base64.b64decode(\'%s\'))"' % base64.b64encode(REBRAND.encode()).decode())
)

app = modal.App("sola-web", image=image)
data = modal.Volume.from_name("sola-web-data", create_if_missing=True)
secrets = [modal.Secret.from_name("sola-web-secrets")]


def _keep_committing(every=30):
    """Persist the SQLite files to the Volume regularly (Modal also commits on shutdown)."""
    def loop():
        while True:
            time.sleep(every)
            try:
                data.commit()
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True, name="volume-commit").start()


@app.function(volumes={"/data": data}, secrets=secrets, max_containers=1, scaledown_window=1200, timeout=900)
@modal.concurrent(max_inputs=200)
@modal.asgi_app()
def web():
    import sys

    sys.path.insert(0, f"{APP}/backend")
    os.chdir(f"{APP}/backend")
    _keep_committing()
    from starlette.responses import PlainTextResponse
    from app.main import app as sola

    async def website_only(scope, receive, send):
        if scope["type"] == "http" and (scope["path"] == "/mobile" or scope["path"].startswith("/mobile/")):
            return await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
        return await sola(scope, receive, send)

    return website_only
