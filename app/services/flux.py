import asyncio
import base64
import logging
from io import BytesIO

import httpx
from PIL import Image

from app.config import FLUX_ENDPOINT, FLUX_API_KEY

logger = logging.getLogger(__name__)

# Flux.2-pro dimension constraints (per BFL docs)
# https://docs.bfl.ai/flux_2/flux2_image_editing
_MIN_DIM = 64
_MAX_PIXELS = 4_000_000  # 4 MP max output
_STEP = 16

# Limit the *input* image so the base64 payload stays within Azure proxy limits.
_INPUT_MAX_PIXELS = 2_000_000  # 2 MP — keeps payload well under size limits
_INPUT_JPEG_QUALITY = 90


def _clamp_dimension(value: int) -> int:
    """Round a dimension to the nearest multiple of 16 (min 64)."""
    clamped = max(_MIN_DIM, value)
    return _STEP * round(clamped / _STEP)


def _clamp_output_dimensions(width: int, height: int) -> tuple[int, int]:
    """Ensure width × height ≤ 4 MP and both are multiples of 16."""
    width = _clamp_dimension(width)
    height = _clamp_dimension(height)
    # Scale down proportionally if total pixels exceed 4 MP
    total = width * height
    if total > _MAX_PIXELS:
        scale = (_MAX_PIXELS / total) ** 0.5
        width = _STEP * round((width * scale) / _STEP)
        height = _STEP * round((height * scale) / _STEP)
        width = max(_MIN_DIM, width)
        height = max(_MIN_DIM, height)
    return width, height


def _prepare_input_image(image_bytes: bytes) -> str:
    """Resize + JPEG-compress the input image to keep the payload small.

    Large source images (phone photos, PNGs, etc.) can easily exceed the Azure
    AI proxy's request-body limit when base64-encoded inside JSON.  Resizing to
    ≤ 2 MP and converting to JPEG keeps the payload well under the limit while
    preserving enough detail for the model.
    """
    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGB")  # drop alpha; JPEG doesn't support it

    # Resize if the input exceeds _INPUT_MAX_PIXELS
    w, h = img.size
    if w * h > _INPUT_MAX_PIXELS:
        scale = (_INPUT_MAX_PIXELS / (w * h)) ** 0.5
        new_w = _STEP * round((w * scale) / _STEP)
        new_h = _STEP * round((h * scale) / _STEP)
        new_w = max(_MIN_DIM, new_w)
        new_h = max(_MIN_DIM, new_h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info(
            "Resized input image from %dx%d to %dx%d for Flux payload",
            w, h, new_w, new_h,
        )

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=_INPUT_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


async def _generate_one(
    client: httpx.AsyncClient,
    image_b64: str,
    prompt: str,
    width: int,
    height: int,
    seed: int | None = None,
) -> str | None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FLUX_API_KEY}",
    }
    payload: dict = {
        "model": "FLUX.2-pro",
        "prompt": prompt,
        # "width": width,
        # "height": height,
        "output_format": "jpeg",
        "safety_tolerance": 5,
        "input_image": image_b64,
    }
    if seed is not None:
        payload["seed"] = seed

    logger.info(
        "Flux request: endpoint=%s, prompt=%r, width=%d, height=%d, seed=%s, image_b64_len=%d",
        FLUX_ENDPOINT, prompt, width, height, seed, len(image_b64),
    )
    logger.debug("Flux payload keys: %s", list(payload.keys()))

    resp = await client.post(FLUX_ENDPOINT, json=payload, headers=headers)

    if resp.status_code != 200:
        logger.error(
            "Flux API error: status=%d, url=%s, body=%s",
            resp.status_code, resp.url, resp.text,
        )
    resp.raise_for_status()

    body = resp.json()
    logger.debug("Flux response body keys: %s", list(body.keys()))

    for item in body.get("data", []):
        b64 = item.get("b64_json", "")
        if b64:
            return f"data:image/jpeg;base64,{b64}"
    return None


async def generate(image_bytes: bytes, prompt: str, width: int, height: int, n: int) -> list[str]:
    width, height = _clamp_output_dimensions(width, height)
    image_b64 = _prepare_input_image(image_bytes)

    logger.info(
        "Flux generate: prompt=%r, dimensions=%dx%d, n=%d, image_b64_len=%d",
        prompt, width, height, n, len(image_b64),
    )

    async with httpx.AsyncClient(timeout=240.0) as client:
        tasks = [_generate_one(client, image_b64, prompt, width, height) for _ in range(n)]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

    images: list[str] = []
    for i, result in enumerate(raw):
        if isinstance(result, Exception):
            logger.error("Flux request %d/%d failed: %s", i + 1, n, result)
        elif result is not None:
            images.append(result)

    logger.info("Flux returned %d image(s) out of %d requested", len(images), n)

    if not images and raw:
        first_exc = next((r for r in raw if isinstance(r, Exception)), None)
        if first_exc is not None:
            raise first_exc

    return images
