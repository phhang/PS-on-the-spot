"""
Standalone test for the Flux API endpoint.

Usage:
    python -m tests.test_flux_endpoint

Uses a real image from the generated/ directory and sends a request
to the configured FLUX_ENDPOINT.  Prints detailed diagnostics so you
can see exactly what the API returns (or rejects).
"""

import asyncio
import base64
import json
import logging
import sys
from pathlib import Path

import httpx
from PIL import Image
from io import BytesIO

# ── bootstrap project config ────────────────────────────────────────
# Add project root to path so we can import app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import FLUX_ENDPOINT, FLUX_API_KEY  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────
GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"
_MIN_DIM = 64
_STEP = 16
_MAX_PIXELS = 4_000_000
_INPUT_MAX_PIXELS = 2_000_000
_INPUT_JPEG_QUALITY = 90


def _pick_test_image() -> Path:
    """Return the first image file found in generated/."""
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        files = sorted(GENERATED_DIR.glob(ext))
        if files:
            return files[0]
    raise FileNotFoundError(f"No images found in {GENERATED_DIR}")


def _prepare_input_image(image_path: Path) -> tuple[str, int, int]:
    """Load, resize, JPEG-compress, and base64-encode the test image.

    Returns (b64_string, width, height).
    """
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    logger.info("Original image: %s  (%d x %d, %.2f MP)", image_path.name, w, h, w * h / 1e6)

    if w * h > _INPUT_MAX_PIXELS:
        scale = (_INPUT_MAX_PIXELS / (w * h)) ** 0.5
        new_w = _STEP * round((w * scale) / _STEP)
        new_h = _STEP * round((h * scale) / _STEP)
        new_w = max(_MIN_DIM, new_w)
        new_h = max(_MIN_DIM, new_h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = new_w, new_h
        logger.info("Resized to %d x %d (%.2f MP)", w, h, w * h / 1e6)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=_INPUT_JPEG_QUALITY)
    b64 = base64.b64encode(buf.getvalue()).decode()
    logger.info("Base64 payload length: %d chars (%.1f KB)", len(b64), len(b64) / 1024)
    return b64, w, h


async def test_flux():
    # ── pre-flight checks ────────────────────────────────────────────
    if not FLUX_ENDPOINT:
        logger.error("FLUX_ENDPOINT is not set in .env")
        sys.exit(1)
    if not FLUX_API_KEY:
        logger.error("FLUX_API_KEY is not set in .env")
        sys.exit(1)

    logger.info("FLUX_ENDPOINT = %s", FLUX_ENDPOINT)
    logger.info("FLUX_API_KEY  = %s…", FLUX_API_KEY[:8])

    # ── prepare image ────────────────────────────────────────────────
    image_path = _pick_test_image()
    image_b64, orig_w, orig_h = _prepare_input_image(image_path)

    prompt = "Apply a cinematic, moody lighting effect to all photos. Make them look like scenes from a sci-fi noir film"

    # ── build payload ────────────────────────────────────────────────
    payload = {
        "model": "FLUX.2-pro",
        "prompt": prompt,
        "output_format": "jpeg",
        "input_image": image_b64,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLUX_API_KEY}",
    }

    logger.info("Request: prompt=%r", prompt)
    payload_json = json.dumps(payload)
    logger.info("Payload size: %.1f KB", len(payload_json) / 1024)

    # ── send request ─────────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=120.0) as client:
        logger.info("Sending POST to %s …", FLUX_ENDPOINT)
        resp = await client.post(FLUX_ENDPOINT, json=payload, headers=headers)

    # ── inspect response ─────────────────────────────────────────────
    logger.info("Response status: %d", resp.status_code)
    logger.info("Response headers: %s", dict(resp.headers))

    try:
        body = resp.json()
        # Truncate any base64 blobs for readable output
        printable = {}
        for k, v in body.items():
            if k == "data" and isinstance(v, list):
                printable[k] = [
                    {kk: (vv[:60] + "…" if isinstance(vv, str) and len(vv) > 60 else vv)
                     for kk, vv in item.items()}
                    for item in v
                ]
            else:
                printable[k] = v
        logger.info("Response body:\n%s", json.dumps(printable, indent=2))
    except Exception:
        logger.info("Response text:\n%s", resp.text[:2000])

    if resp.status_code == 200:
        logger.info("SUCCESS — Flux API returned 200")
        # Optionally save the result
        for i, item in enumerate(body.get("data", [])):
            b64 = item.get("b64_json", "")
            if b64:
                out_path = GENERATED_DIR / f"test_flux_result_{i}.jpg"
                out_path.write_bytes(base64.b64decode(b64))
                logger.info("Saved result image: %s", out_path)
    else:
        logger.error("FAILED — Flux API returned %d", resp.status_code)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(test_flux())
