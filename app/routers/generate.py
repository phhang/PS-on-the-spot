import base64
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile, HTTPException, Query
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.config import DATA_DIR, GENERATED_DIR
from app.services import gpt_image, flux

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

_generated_dir = Path(GENERATED_DIR)
_generated_dir.mkdir(parents=True, exist_ok=True)
_history_file = Path(DATA_DIR) / "generated_history.json"

_RECENT_LIMIT = 10
_HISTORY_CAP = 200


def _read_history() -> list[dict]:
    if not _history_file.exists():
        return []

    try:
        return json.loads(_history_file.read_text())
    except json.JSONDecodeError:
        logger.exception("Failed to parse generation history file: %s", _history_file)
        return []


def _write_history(entries: list[dict]) -> None:
    _history_file.parent.mkdir(parents=True, exist_ok=True)
    _history_file.write_text(json.dumps(entries[:_HISTORY_CAP], indent=2))


def _append_history(entries: list[dict]) -> None:
    if not entries:
        return

    history = _read_history()
    _write_history(entries + history)


def _save_image(
    data_uri: str,
    original_filename: str,
    prompt: str,
    model: str,
    job_id: str,
    index: int,
    submitted_at: str,
) -> dict:
    """Decode a data-URI image, embed the prompt in EXIF + PNG metadata, and save to disk."""
    # Parse data URI: "data:image/<fmt>;base64,<b64>"
    _header, b64_data = data_uri.split(",", 1)
    image_bytes = base64.b64decode(b64_data)

    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGBA") if img.mode == "RGBA" else img.convert("RGB")

    # PNG tEXt chunk (readable by Pillow, exiftool, etc.)
    metadata = PngInfo()
    metadata.add_text("prompt", prompt)

    # EXIF metadata — visible in Windows Explorer Details tab
    exif = img.getexif()
    # 270 = ImageDescription — shows as "Title" / "Subject" in Windows
    exif[270] = prompt
    # 40092 = XPComment — shows as "Comments" in Windows Photo Viewer / Explorer Details
    exif[40092] = prompt.encode("utf-16-le") + b"\x00\x00"
    # 40091 = XPTitle — shows as "Title" in Windows Explorer Details
    exif[40091] = prompt.encode("utf-16-le") + b"\x00\x00"

    stem = Path(original_filename).stem
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{stem}_{timestamp}_{index}.png"

    out_path = _generated_dir / filename
    img.save(str(out_path), format="PNG", pnginfo=metadata, exif=exif.tobytes())
    logger.info("Saved generated image: %s", out_path)

    return {
        "id": str(uuid4()),
        "job_id": job_id,
        "filename": filename,
        "url": f"/generated/{filename}",
        "prompt": prompt,
        "model": model,
        "submitted_at": submitted_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": original_filename,
    }


async def _generate_and_store(
    image_bytes: bytes,
    original_filename: str,
    model: str,
    prompt: str,
    width: int,
    height: int,
    n: int,
    job_id: str,
    submitted_at: str,
) -> None:
    logger.info(
        "Starting background generation: job_id=%s model=%s prompt=%r width=%d height=%d n=%d",
        job_id,
        model,
        prompt,
        width,
        height,
        n,
    )

    try:
        if model == "gpt-image-1.5":
            images = await gpt_image.generate(image_bytes, prompt, width, height, n)
        elif model == "FLUX.2-pro":
            images = await flux.generate(image_bytes, prompt, width, height, n)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model}")
    except HTTPException:
        logger.exception("Background generation rejected: job_id=%s", job_id)
        return
    except Exception:
        logger.exception("Background generation failed: job_id=%s", job_id)
        return

    history_entries: list[dict] = []
    for i, data_uri in enumerate(images):
        try:
            history_entries.append(
                _save_image(data_uri, original_filename, prompt, model, job_id, i, submitted_at)
            )
        except Exception:
            logger.exception("Failed to save image %d to disk for job %s", i, job_id)

    _append_history(history_entries)
    logger.info(
        "Completed background generation: job_id=%s saved=%d/%d",
        job_id,
        len(history_entries),
        len(images),
    )


@router.post("/generate", status_code=202)
async def generate_images(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    model: str = Form(...),
    prompt: str = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    n: int = Form(1),
):
    image_bytes = await image.read()
    original_filename = image.filename or "image"
    job_id = str(uuid4())
    submitted_at = datetime.now(timezone.utc).isoformat()

    if model not in {"gpt-image-1.5", "FLUX.2-pro"}:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model}")

    background_tasks.add_task(
        _generate_and_store,
        image_bytes,
        original_filename,
        model,
        prompt,
        width,
        height,
        n,
        job_id,
        submitted_at,
    )

    return {
        "status": "queued",
        "job_id": job_id,
        "prompt": prompt,
        "model": model,
        "submitted_at": submitted_at,
    }


@router.get("/generations/recent")
async def recent_generations(limit: int = Query(_RECENT_LIMIT, ge=1, le=50)):
    history = _read_history()
    return {"items": history[:limit]}
