# Image Enhancer Web App

Internal web app for uploading photos and enhancing them using Microsoft Foundry image models (gpt-image-1.5, FLUX.2-pro), via image to image generation.

## Tech Stack

- **Backend**: Python 3 + FastAPI (serves API + static files)
- **Frontend**: Vanilla HTML/CSS/JS (no build step)
- **Storage**: JSON file on disk (`data/presets.json`)

## Project Structure

```
ps_on_the_spot/
├── app/
│   ├── main.py              # FastAPI app, mounts routers + static files
│   ├── config.py             # Env var config (endpoints, API keys)
│   ├── routers/
│   │   ├── generate.py       # POST /api/generate
│   │   └── presets.py        # CRUD /api/presets
│   └── services/
│       ├── gpt_image.py      # OpenAI SDK image edit calls
│       └── flux.py           # FLUX.2-pro REST API calls
├── static/
│   ├── index.html            # Single-page app
│   ├── style.css
│   └── app.js
├── data/
│   └── presets.json          # Preset prompts (persisted on disk)
├── venv/                     # Python virtual environment
├── requirements.txt
└── .env.example
```

## Setup & Running

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in real endpoints/keys
venv/bin/uvicorn app.main:app --reload
# Or venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 9112
# Open http://localhost:8000
```

## Environment Variables

| Variable | Description |
|---|---|
| `GPT_IMAGE_ENDPOINT` | OpenAI-compatible base URL for gpt-image-1.5 |
| `GPT_IMAGE_API_KEY` | API key for gpt-image-1.5 |
| `FLUX_ENDPOINT` | FLUX.2-pro endpoint URL |
| `FLUX_API_KEY` | API key for FLUX.2-pro |
| `DATA_DIR` | Path to data directory (default `./data`) |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/generate` | Multipart form: image, model, prompt, width, height, n. Returns `{ "images": ["data:image/png;base64,..."] }` |
| GET | `/api/presets` | List all preset prompts |
| POST | `/api/presets` | Create preset `{ "name", "prompt" }` |
| PUT | `/api/presets/{id}` | Update a preset |
| DELETE | `/api/presets/{id}` | Delete a preset |

## Key Conventions

- No authentication — handled by reverse proxy.
- gpt-image-1.5 uses the OpenAI Python SDK (`client.images.edit`) with a custom `base_url`.
- FLUX.2-pro API reference: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure?view=foundry-classic&tabs=global-standard-aoai%2Cglobal-standard&pivots=azure-direct-others#code-samples-for-flux2-models
- FLUX.2-pro parameters: https://docs.bfl.ai/flux_2/flux2_image_editing#flux-2-image-editing-parameters
- Presets are stored as a flat JSON array in `data/presets.json` with `{ id, name, prompt }` objects.
- Frontend is a single-page app with no build tooling — edit `static/` files directly.
- All Python dependencies are in `venv/`; always use `venv/bin/pip` and `venv/bin/uvicorn`.
- Safety/moderation will be handled by other API, use safety_tolerance = 5 (more permissive) for FLUX.2-pro and moderation = low for gpt-image-1.5.