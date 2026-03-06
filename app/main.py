from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import generate, presets

app = FastAPI(title="Image Enhancer")

app.include_router(generate.router)
app.include_router(presets.router)

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

import logging
logging.basicConfig(level=logging.INFO)