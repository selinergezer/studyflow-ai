import requests
from typing import Any
from app.core.config import settings


OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL = settings.OLLAMA_MODEL


def generate_with_ollama(
    prompt: str,
    response_schema: dict[str, Any] | None = None
) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    if response_schema is not None:
        payload["format"] = response_schema

    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=300,
    )

    response.raise_for_status()

    data = response.json()

    return data["response"].strip()