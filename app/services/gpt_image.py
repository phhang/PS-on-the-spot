import logging
from io import BytesIO

from openai import AsyncAzureOpenAI

from app.config import GPT_IMAGE_ENDPOINT, GPT_IMAGE_API_KEY

logger = logging.getLogger(__name__)

SUPPORTED_SIZES = ["1024x1024", "1024x1536", "1536x1024"]


def _pick_best_size(width: int, height: int) -> str:
    """Map arbitrary dimensions to the closest supported GPT-Image size."""
    aspect = width / height
    # 1536x1024 = 1.5, 1024x1024 = 1.0, 1024x1536 ≈ 0.667
    if aspect > 1.25:
        return "1536x1024"
    elif aspect < 0.8:
        return "1024x1536"
    return "1024x1024"


def _get_client() -> AsyncAzureOpenAI:
    return AsyncAzureOpenAI(
        azure_endpoint=GPT_IMAGE_ENDPOINT,
        api_key=GPT_IMAGE_API_KEY,
        api_version="2025-04-01-preview",
        azure_deployment="gpt-image-1.5",
    )


async def generate(image_bytes: bytes, prompt: str, width: int, height: int, n: int) -> list[str]:
    client = _get_client()
    size = _pick_best_size(width, height)
    image_file = BytesIO(image_bytes)
    image_file.name = "upload.png"

    logger.info(
        "GPT-Image request: prompt=%r, requested=%dx%d, mapped_size=%s, n=%d, image_size=%d bytes",
        prompt, width, height, size, n, len(image_bytes),
    )

    try:
        response = await client.images.edit(
            image=image_file,
            prompt=prompt,
            size=size,
            n=n,
            input_fidelity="high",
        )
    except Exception:
        logger.exception(
            "GPT-Image API call failed: endpoint=%s, deployment=gpt-image-1.5, "
            "api_version=2025-04-01-preview, size=%s, n=%d, image_size=%d bytes",
            GPT_IMAGE_ENDPOINT, size, n, len(image_bytes),
        )
        raise

    results: list[str] = []
    for item in response.data:
        if item.b64_json:
            results.append(f"data:image/png;base64,{item.b64_json}")
        elif item.url:
            results.append(item.url)

    logger.info("GPT-Image returned %d image(s)", len(results))
    return results
