"""Serve the built React app from FastAPI, so production is one URL with no CORS.

Unknown paths fall back to index.html, so a browser refresh on a client-side route
(e.g. /orders/12, added in P8) still loads the app. Paths under /api never fall back:
a wrong API URL must stay a JSON 404, not an HTML page.
"""

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("api"):
                raise
            return await super().get_response("index.html", scope)
