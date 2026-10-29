"""
Optional semantic matching. Turns page text into vectors with ANY OpenAI-compatible
`/embeddings` endpoint (OpenAI, Azure OpenAI, a local server...). Switched off unless configured.

If the provider fails, the analysis continues WITHOUT semantic scores and says so in its report.
"""
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    pass


def is_configured():
    return bool(settings.EMBEDDINGS_ENABLED and settings.EMBEDDINGS_API_KEY and settings.EMBEDDINGS_MODEL)


def embedding_text(page):
    """Title + heading + description when we have them, otherwise the words of the URL path."""
    text = " ".join(part for part in (page.title, page.h1, page.meta) if part)
    return (text or " ".join(page.path_tokens))[:1000]


def _post(batch):
    url = settings.EMBEDDINGS_BASE_URL.rstrip("/") + "/embeddings"
    last_error = "unknown error"
    for attempt in range(3):  # small retry budget for temporary provider trouble
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}"},
                json={"model": settings.EMBEDDINGS_MODEL, "input": batch},
                timeout=settings.EMBEDDINGS_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = f"network error ({exc.__class__.__name__})"
        else:
            if response.status_code == 200:
                try:
                    items = sorted(response.json()["data"], key=lambda item: item["index"])
                    vectors = [item["embedding"] for item in items]
                except (KeyError, ValueError, TypeError):
                    raise EmbeddingError("The embedding provider returned an unexpected response.")
                if len(vectors) != len(batch):
                    raise EmbeddingError("The embedding provider returned the wrong number of vectors.")
                return vectors
            if response.status_code in (401, 403):
                raise EmbeddingError("The embedding provider rejected the API key.")
            if response.status_code == 404:
                raise EmbeddingError("The embedding model or endpoint was not found. Check EMBEDDINGS_MODEL and EMBEDDINGS_BASE_URL.")
            last_error = f"provider error {response.status_code}"
            if response.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(1 + attempt)
    raise EmbeddingError(f"The embedding provider could not be reached ({last_error}).")


def embed_texts(texts):
    """Return one vector per text, in order. Raises EmbeddingError on failure."""
    vectors = []
    size = max(1, settings.EMBEDDINGS_BATCH_SIZE)
    for start in range(0, len(texts), size):
        vectors.extend(_post(texts[start : start + size]))
    return vectors
