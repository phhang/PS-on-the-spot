import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import DATA_DIR

router = APIRouter(prefix="/api/presets", tags=["presets"])

PRESETS_FILE = Path(DATA_DIR) / "presets.json"


class PresetIn(BaseModel):
    name: str
    prompt: str


def _read_presets() -> list[dict]:
    if not PRESETS_FILE.exists():
        return []
    return json.loads(PRESETS_FILE.read_text())


def _write_presets(presets: list[dict]) -> None:
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_FILE.write_text(json.dumps(presets, indent=2))


@router.get("")
async def list_presets():
    return _read_presets()


@router.post("", status_code=201)
async def create_preset(body: PresetIn):
    presets = _read_presets()
    preset = {"id": str(uuid.uuid4()), "name": body.name, "prompt": body.prompt}
    presets.append(preset)
    _write_presets(presets)
    return preset


@router.put("/{preset_id}")
async def update_preset(preset_id: str, body: PresetIn):
    presets = _read_presets()
    for p in presets:
        if p["id"] == preset_id:
            p["name"] = body.name
            p["prompt"] = body.prompt
            _write_presets(presets)
            return p
    raise HTTPException(status_code=404, detail="Preset not found")


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(preset_id: str):
    presets = _read_presets()
    filtered = [p for p in presets if p["id"] != preset_id]
    if len(filtered) == len(presets):
        raise HTTPException(status_code=404, detail="Preset not found")
    _write_presets(filtered)
