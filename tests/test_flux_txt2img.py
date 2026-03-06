"""
Test for the Flux text-to-image API endpoint (no input image required).

Mirrors the documented curl example:

    curl -X POST "<ENDPOINT>/providers/blackforestlabs/v1/flux-2-pro?api-version=preview" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $AZURE_API_KEY" \
      -d '{
            "prompt" : "A photograph of a red fox in an autumn forest",
            "width" : 1024,
            "height" : 1024,
            "n" : 1,
            "model": "FLUX.2-pro"
        }'

Usage:
    python -m tests.test_flux_txt2img          # uses FLUX_ENDPOINT / FLUX_API_KEY from .env
    python -m pytest tests/test_flux_txt2img.py -v   # pytest runner (markers: integration)
"""

import asyncio
import base64
import json
import logging
import os
import sys
from pathlib import Path

import httpx
import pytest

# ── bootstrap project config ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import FLUX_API_KEY  # noqa: E402

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────
GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# The text-to-image endpoint from the curl example.
# Allow override via env var; fall back to the documented URL.
TXT2IMG_ENDPOINT = os.getenv(
    "FLUX_TXT2IMG_ENDPOINT",
    "https://ai-aihubtest880392662253.services.ai.azure.com"
    "/providers/blackforestlabs/v1/flux-2-pro?api-version=preview",
)

DEFAULT_PROMPT = "A photograph of a red fox in an autumn forest"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_N = 1
DEFAULT_MODEL = "FLUX.2-pro"


# ── helpers ──────────────────────────────────────────────────────────

def _build_headers() -> dict[str, str]:
    """Build request headers matching the curl example (Bearer auth)."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLUX_API_KEY}",
    }


def _build_payload(
    prompt: str = DEFAULT_PROMPT,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    n: int = DEFAULT_N,
    model: str = DEFAULT_MODEL,
) -> dict:
    return {
        "prompt": prompt,
        "width": width,
        "height": height,
        "n": n,
        "model": model,
    }


def _save_result_images(body: dict) -> list[Path]:
    """Decode and save any base64 images from the response."""
    saved: list[Path] = []
    for i, item in enumerate(body.get("data", [])):
        b64 = item.get("b64_json", "")
        if b64:
            out_path = GENERATED_DIR / f"test_flux_txt2img_{i}.png"
            out_path.write_bytes(base64.b64decode(b64))
            logger.info("Saved result image: %s", out_path)
            saved.append(out_path)
    return saved


# ── async core ───────────────────────────────────────────────────────

async def _call_flux_txt2img(
    prompt: str = DEFAULT_PROMPT,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    n: int = DEFAULT_N,
    model: str = DEFAULT_MODEL,
    timeout: float = 120.0,
) -> httpx.Response:
    """Send a text-to-image request to the Flux endpoint."""
    headers = _build_headers()
    payload = _build_payload(prompt, width, height, n, model)

    logger.info("Endpoint : %s", TXT2IMG_ENDPOINT)
    logger.info("Payload  : %s", json.dumps(payload, indent=2))
    logger.info("Key hint : %s…", FLUX_API_KEY[:8] if FLUX_API_KEY else "<unset>")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(TXT2IMG_ENDPOINT, json=payload, headers=headers)

    logger.info("Status   : %d", resp.status_code)
    logger.info("Headers  : %s", dict(resp.headers))

    try:
        body = resp.json()
        # Truncate base64 blobs for readability
        printable: dict = {}
        for k, v in body.items():
            if k == "data" and isinstance(v, list):
                printable[k] = [
                    {
                        kk: (vv[:60] + "…" if isinstance(vv, str) and len(vv) > 60 else vv)
                        for kk, vv in item.items()
                    }
                    for item in v
                ]
            else:
                printable[k] = v
        logger.info("Body     :\n%s", json.dumps(printable, indent=2))
    except Exception:
        logger.info("Body (raw):\n%s", resp.text[:2000])

    return resp


# ── pytest integration tests ─────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.skipif(not FLUX_API_KEY, reason="FLUX_API_KEY not set")
@pytest.mark.asyncio
async def test_txt2img_returns_200():
    """POST with the example payload should return 200 and at least one image."""
    resp = await _call_flux_txt2img()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"

    body = resp.json()
    data = body.get("data", [])
    assert len(data) >= 1, f"Expected at least 1 image in data, got {len(data)}"
    assert data[0].get("b64_json"), "First image has no b64_json field"

    saved = _save_result_images(body)
    assert len(saved) >= 1, "No images were saved to disk"
    for p in saved:
        assert p.stat().st_size > 0, f"Saved image {p} is empty"


@pytest.mark.integration
@pytest.mark.skipif(not FLUX_API_KEY, reason="FLUX_API_KEY not set")
@pytest.mark.asyncio
async def test_txt2img_b64_decodes_to_valid_image():
    """The returned base64 payload should decode to a valid image file."""
    resp = await _call_flux_txt2img()
    assert resp.status_code == 200

    body = resp.json()
    b64 = body["data"][0]["b64_json"]
    image_bytes = base64.b64decode(b64)

    # Verify the bytes are a valid image (PNG or JPEG)
    assert len(image_bytes) > 100, "Decoded image is suspiciously small"

    # Check magic bytes: PNG (‰PNG) or JPEG (ÿØÿ)
    is_png = image_bytes[:4] == b"\x89PNG"
    is_jpeg = image_bytes[:2] == b"\xff\xd8"
    assert is_png or is_jpeg, (
        f"Decoded bytes don't look like PNG or JPEG (first 4 bytes: {image_bytes[:4]!r})"
    )


@pytest.mark.integration
@pytest.mark.skipif(not FLUX_API_KEY, reason="FLUX_API_KEY not set")
@pytest.mark.asyncio
async def test_txt2img_custom_dimensions():
    """Requesting a non-square image should succeed."""
    resp = await _call_flux_txt2img(width=1024, height=768)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:500]}"

    body = resp.json()
    assert len(body.get("data", [])) >= 1


@pytest.mark.integration
@pytest.mark.skipif(not FLUX_API_KEY, reason="FLUX_API_KEY not set")
@pytest.mark.asyncio
async def test_txt2img_missing_prompt_returns_error():
    """An empty prompt should be rejected by the API."""
    resp = await _call_flux_txt2img(prompt="")
    # Most APIs return 400 or 422 for invalid input
    assert resp.status_code in (400, 422, 500), (
        f"Expected error status for empty prompt, got {resp.status_code}"
    )


# ── standalone runner ─────────────────────────────────────────────────

async def main():
    """Run the basic smoke test and save the output image."""
    if not FLUX_API_KEY:
        logger.error("FLUX_API_KEY is not set in .env — aborting")
        sys.exit(1)

    resp = await _call_flux_txt2img()

    if resp.status_code == 200:
        body = resp.json()
        saved = _save_result_images(body)
        logger.info("SUCCESS — %d image(s) saved", len(saved))
    else:
        logger.error("FAILED — status %d", resp.status_code)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
