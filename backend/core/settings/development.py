"""Local development only. Never use these settings on a public server."""
from .base import *  # noqa: F401,F403
from .base import CORS_ALLOWED_ORIGINS, env_bool

DEBUG = env_bool("DEBUG", True)
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
