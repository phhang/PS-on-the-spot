from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import GENERATED_DIR
from app.routers import generate, presets

app = FastAPI(title="Image Enhancer")

app.include_router(generate.router)
app.include_router(presets.router)

static_dir = Path(__file__).resolve().parent.parent / "static"
generated_dir = Path(GENERATED_DIR)
generated_dir.mkdir(parents=True, exist_ok=True)

app.mount("/generated", StaticFiles(directory=str(generated_dir)), name="generated")
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

import logging
logging.basicConfig(level=logging.INFO)