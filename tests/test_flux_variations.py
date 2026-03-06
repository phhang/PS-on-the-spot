"""
Diagnostic test for Flux API — tries multiple payload variations
to isolate the cause of the 500 error.

Usage:
    venv/bin/python -m tests.test_flux_variations
"""

import asyncio
import base64
import json
import logging
import sys
from pathlib import Path
from io import BytesIO
from copy import deepcopy

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import FLUX_ENDPOINT, FLUX_API_KEY

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"
_STEP = 16
_MIN_DIM = 64


def _pick_test_image() -> Path:
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        files = sorted(GENERATED_DIR.glob(ext))
        if files:
            return files[0]
    raise FileNotFoundError(f"No images in {GENERATED_DIR}")


def _make_small_test_image(size: tuple[int, int] = (256, 256)) -> str:
    """Create a tiny solid-color JPEG image for minimal testing."""
    img = Image.new("RGB", size, color=(128, 100, 80))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _load_and_encode(path: Path, max_dim: int = 512) -> str:
    """Load a real image, resize to max_dim, JPEG-encode, base64."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(max_dim / w, max_dim / h, 1.0)
    nw = _STEP * round((w * scale) / _STEP)
    nh = _STEP * round((h * scale) / _STEP)
    nw, nh = max(_MIN_DIM, nw), max(_MIN_DIM, nh)
    img = img.resize((nw, nh), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    logger.info("Encoded %s → %dx%d, %d chars b64", path.name, nw, nh, len(b64))
    return b64


async def _try_request(
    client: httpx.AsyncClient,
    label: str,
    endpoint: str,
    headers: dict,
    payload: dict,
) -> dict:
    """Send a request and return summary info."""
    # Don't log image data
    log_payload = {k: (f"<{len(v)} chars>" if k.startswith("input_image") and isinstance(v, str) and len(v) > 100 else v) for k, v in payload.items()}
    logger.info("─── Test: %s ───", label)
    logger.info("  Endpoint: %s", endpoint)
    logger.info("  Payload: %s", json.dumps(log_payload, indent=4))

    try:
        resp = await client.post(endpoint, json=payload, headers=headers)
    except Exception as e:
        logger.error("  Connection error: %s", e)
        return {"label": label, "status": "error", "detail": str(e)}

    result = {
        "label": label,
        "status": resp.status_code,
        "headers": dict(resp.headers),
    }

    try:
        body = resp.json()
        # Truncate base64 blobs
        safe = {}
        for k, v in body.items():
            if k == "data" and isinstance(v, list):
                safe[k] = [
                    {kk: (f"<{len(vv)} chars b64>" if isinstance(vv, str) and len(vv) > 200 else vv)
                     for kk, vv in item.items()}
                    for item in v
                ]
            else:
                safe[k] = v
        result["body"] = safe
    except Exception:
        result["body_text"] = resp.text[:1000]

    status_icon = "✓" if resp.status_code == 200 else "✗"
    logger.info("  %s Status: %d", status_icon, resp.status_code)
    logger.info("  Response: %s", json.dumps(result.get("body", result.get("body_text", "")), indent=4))

    return result


async def run_tests():
    if not FLUX_ENDPOINT or not FLUX_API_KEY:
        logger.error("FLUX_ENDPOINT or FLUX_API_KEY not set")
        sys.exit(1)

    logger.info("Endpoint: %s", FLUX_ENDPOINT)
    logger.info("API Key:  %s…", FLUX_API_KEY[:8])

    real_image_path = _pick_test_image()
    real_b64 = _load_and_encode(real_image_path, max_dim=512)
    tiny_b64 = _make_small_test_image((256, 256))

    base_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLUX_API_KEY}",
    }

    # Alternative auth header (api-key style)
    apikey_headers = {
        "api-key": FLUX_API_KEY,
        "Content-Type": "application/json",
    }

    # Alternative auth header (BFL native uses x-key)
    bfl_headers = {
        "x-key": FLUX_API_KEY,
        "Content-Type": "application/json",
    }

    tests = []

    # --- Test 1: Minimal payload matching official API example ---
    tests.append(("1. Official API format", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "Apply a cinematic, moody lighting effect to all photos",
        "output_format": "jpeg",
        "input_image": tiny_b64,
    }))

    # --- Test 2: Real image, official format ---
    tests.append(("2. Real image, official format", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a simple test",
        "output_format": "jpeg",
        "input_image": real_b64,
    }))

    # --- Test 3: With input_image_2 (two input images) ---
    tests.append(("3. Two input images", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "Combine these two images into a single scene",
        "output_format": "jpeg",
        "input_image": real_b64,
        "input_image_2": tiny_b64,
    }))

    # --- Test 4: With data URI prefix on image ---
    tests.append(("4. Data URI prefix", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a simple test",
        "output_format": "jpeg",
        "input_image": f"data:image/jpeg;base64,{tiny_b64}",
    }))

    # --- Test 5: Using api-key header ---
    tests.append(("5. api-key auth", FLUX_ENDPOINT, apikey_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a test",
        "output_format": "jpeg",
        "input_image": tiny_b64,
    }))

    # --- Test 6: Using BFL x-key header ---
    tests.append(("6. x-key auth", FLUX_ENDPOINT, bfl_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a test",
        "output_format": "jpeg",
        "input_image": tiny_b64,
    }))

    # --- Test 7: Try png output format ---
    tests.append(("7. PNG output", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a test",
        "output_format": "png",
        "input_image": tiny_b64,
    }))

    # --- Test 8: Without model field ---
    tests.append(("8. No model field", FLUX_ENDPOINT, base_headers, {
        "prompt": "a test",
        "output_format": "jpeg",
        "input_image": tiny_b64,
    }))

    # --- Test 9: Just prompt, no image (text-to-image) ---
    tests.append(("9. No image at all", FLUX_ENDPOINT, base_headers, {
        "model": "FLUX.2-pro",
        "prompt": "a blue sky",
        "output_format": "jpeg",
    }))

    results = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for label, endpoint, headers, payload in tests:
            result = await _try_request(client, label, endpoint, headers, payload)
            results.append(result)
            await asyncio.sleep(1)  # brief pause between requests

    # --- Summary ---
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    for r in results:
        status = r["status"]
        icon = "✓" if status == 200 else "✗"
        logger.info("  %s [%s] %s", icon, status, r["label"])

    success = [r for r in results if r["status"] == 200]
    if success:
        logger.info("\nSUCCESS: %d test(s) passed!", len(success))
    else:
        logger.info("\nAll tests returned errors. The issue is likely server-side.")


if __name__ == "__main__":
    asyncio.run(run_tests())
