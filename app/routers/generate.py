import base64
import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile, HTTPException
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from app.config import GENERATED_DIR
from app.services import gpt_image, flux

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["generate"])

_generated_dir = Path(GENERATED_DIR)
_generated_dir.mkdir(parents=True, exist_ok=True)


def _save_image(data_uri: str, original_filename: str, prompt: str, index: int) -> None:
    """Decode a data-URI image, embed the prompt in EXIF + PNG metadata, and save to disk."""
    # Parse data URI: "data:image/<fmt>;base64,<b64>"
    header, b64_data = data_uri.split(",", 1)
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


@router.post("/generate")
async def generate_images(
    image: UploadFile = File(...),
    model: str = Form(...),
    prompt: str = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    n: int = Form(4),
):
    image_bytes = await image.read()
    original_filename = image.filename or "image"

    try:
        if model == "gpt-image-1.5":
            images = await gpt_image.generate(image_bytes, prompt, width, height, n)
        elif model == "FLUX.2-pro":
            images = await flux.generate(image_bytes, prompt, width, height, n)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown model: {model}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    for i, data_uri in enumerate(images):
        try:
            _save_image(data_uri, original_filename, prompt, i)
        except Exception:
            logger.exception("Failed to save image %d to disk", i)

    return {"images": images}
