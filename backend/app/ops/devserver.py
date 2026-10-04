"""Development only: the API and the admin panel (web/public) on one origin, as nginx serves them in production.

uvicorn app.ops.devserver:app --reload     # then open http://localhost:8000/admin.html
"""

import os
import pathlib

from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.main import create_app

if get_settings().is_production:
    raise RuntimeError("the development server must not be used in production: nginx serves web/public")

ROOT = pathlib.Path(__file__).resolve().parents[3]

app = create_app()
# the map file, as nginx serves it from deploy/maps (MAPS_DIR: another folder holding kuwait.pmtiles)
maps = pathlib.Path(os.environ.get("MAPS_DIR", ROOT / "deploy" / "maps"))
if maps.is_dir():
    app.mount("/maps", StaticFiles(directory=maps))
app.mount("/", StaticFiles(directory=ROOT / "web" / "public", html=True))
