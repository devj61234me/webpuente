"""Same as the normal test settings, but runs on the MySQL/MariaDB database from .env (Django creates a separate test_ database)."""
from .test import *  # noqa: F401,F403
from .base import DATABASES as _REAL_DATABASES

DATABASES = _REAL_DATABASES
