import os
from dotenv import load_dotenv

load_dotenv()

_default_history_db = os.path.join(os.getenv("DATA_DIR", "./data"), "generated_history.db")

GPT_IMAGE_ENDPOINT = os.getenv("GPT_IMAGE_ENDPOINT", "")
GPT_IMAGE_API_KEY = os.getenv("GPT_IMAGE_API_KEY", "")
FLUX_ENDPOINT = os.getenv("FLUX_ENDPOINT", "")
FLUX_API_KEY = os.getenv("FLUX_API_KEY", "")
DATA_DIR = os.getenv("DATA_DIR", "./data")
GENERATED_DIR = os.getenv("GENERATED_DIR", "./generated")
GENERATED_HISTORY_DB = os.getenv("GENERATED_HISTORY_DB", _default_history_db)
