"""Development only: the API and the admin panel (web/public) on one origin, as nginx serves them in production.

uvicorn app.ops.devserver:app --reload     # then open http://localhost:8000/admin.html
"""

import pathlib

from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.main import create_app

if get_settings().is_production:
    raise RuntimeError("the development server must not be used in production: nginx serves web/public")

app = create_app()
app.mount("/", StaticFiles(directory=pathlib.Path(__file__).resolve().parents[3] / "web" / "public", html=True))
