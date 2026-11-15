"""Deploy the Sola mobile app on Modal: sign-in only, with the demo account.

    python3 -m pip install modal
    python3 -m modal token new
    python3 -m modal secret create sola-mobile-secrets PLACEHOLDER=1   # or real keys, see below
    python3 -m modal deploy modal_app.py

Modal prints https://<workspace>--sola-mobile-web.modal.run. Opening it goes straight
to the mobile app (the website is not served). There is no registration: people sign
in to the demo account, which is created on first start with the prototype's data
(memories, shopping list, laundry camera pictures, door events, health, chat...).
Everything they change is saved on the `sola-mobile-data` Volume and survives redeploys.

Optional:
  * Use your own local data instead of the fresh demo data (stop the local server
    first, then upload before the first deploy, or redeploy afterwards):
        python3 -m modal volume put sola-mobile-data backend/data/taimi.sqlite3 /sola.sqlite3
  * Live search/media/chat model: put any keys you have in the secret instead, e.g.
        python3 -m modal secret create sola-mobile-secrets --force EXA_API_KEY=... CLOUDINARY_URL=... ANTHROPIC_API_KEY=...
    Without keys the app uses its labelled demo data. TEST_ACCOUNT_PASSWORD in the
    secret changes the demo password (applies when the account is first created).
"""
import threading
import time
from pathlib import Path

import modal

ROOT = Path(__file__).parent
APP = "/app"
HF = "https://huggingface.co"
TJS = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1"
VENDOR = f"{APP}/backend/app/static/vendor"


def _model_downloads():
    """Same files as backend/scripts/fetch_edge_models.sh (on-device laundry camera)."""
    cmds = [f"mkdir -p {VENDOR}/models"]
    for f in ("dist/transformers.min.js", "dist/ort-wasm-simd-threaded.jsep.mjs", "dist/ort-wasm-simd-threaded.jsep.wasm"):
        cmds.append(f"curl -fsSL --retry 3 -o {VENDOR}/{f.split('/')[-1]} {TJS}/{f}")
    files = [(m, f) for m in ("Xenova/owlvit-base-patch32", "Xenova/clip-vit-base-patch32")
             for f in ("config.json", "tokenizer.json", "tokenizer_config.json", "preprocessor_config.json", "special_tokens_map.json")]
    files += [("Xenova/owlvit-base-patch32", "onnx/model_quantized.onnx"),
              ("Xenova/clip-vit-base-patch32", "onnx/vision_model_quantized.onnx"),
              ("Xenova/clip-vit-base-patch32", "onnx/text_model_quantized.onnx")]
    for m, f in files:
        cmds.append(f"mkdir -p $(dirname {VENDOR}/models/{m}/{f}) && curl -fsSL --retry 3 -o {VENDOR}/models/{m}/{f} {HF}/{m}/resolve/main/{f}")
    return cmds


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl")
    .pip_install_from_requirements(str(ROOT / "backend" / "requirements.txt"))
    .run_commands(*_model_downloads())
    .env({
        "MOBILE_ONLY": "1",
        "ALLOW_REGISTRATION": "0",
        "SHOW_DEMO_PASSWORD": "1",
        "COOKIE_SECURE": "1",
        "TAIMI_DB": "/data/sola.sqlite3",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    .add_local_dir(str(ROOT / "backend" / "app"), f"{APP}/backend/app", ignore=["**/__pycache__", "static/vendor/**"])
    .add_local_dir(str(ROOT / "mobile"), f"{APP}/mobile")
)

app = modal.App("sola-mobile", image=image)
data = modal.Volume.from_name("sola-mobile-data", create_if_missing=True)
secrets = [modal.Secret.from_name("sola-mobile-secrets")]


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
    import os
    import sys

    sys.path.insert(0, f"{APP}/backend")
    os.chdir(f"{APP}/backend")
    _keep_committing()
    from app.main import app as sola  # / -> /mobile/, /login, /mobile/, /api/...
    return sola
