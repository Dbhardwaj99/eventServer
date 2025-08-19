from datetime import datetime
import json
import os
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn
from copy import deepcopy

from app.state import REQUEST_LOG, LOG_LOCK
from app.utils import now_ist_str, pretty_json

app = FastAPI(title="Event Server", version="1.1.0")

templates = Jinja2Templates(directory="templates")

# CORS support (open to all for demo/demo purposes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with LOG_LOCK:
        items: List[Dict[str, Any]] = list(reversed(REQUEST_LOG))
    # Pre-format JSON for display and avoid JS braces escaping issues
    display_items = [
        {
            **item,
            "json_pretty": pretty_json(item.get("json")),
        }
        for item in items
    ]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "items": display_items,
        },
    )


@app.get("/events-view", response_class=HTMLResponse)
async def events_view(request: Request):
    # Serve the realtime events viewer (client polls /events-feed)
    return templates.TemplateResponse("events.html", {"request": request})


@app.get("/events-tracker", response_class=HTMLResponse)
async def events_tracker(request: Request):
    # 3-pane tracker UI for selected event names
    return templates.TemplateResponse("events_tracker.html", {"request": request})


@app.get("/events-feed")
async def events_feed():
    """
    Flatten and return all events found inside the JSON bodies we've received,
    assuming a structure like { "events": [ ... ] } as provided by the client.
    """
    flattened: List[Dict[str, Any]] = []
    with LOG_LOCK:
        for entry in REQUEST_LOG:
            payload = entry.get("json")
            if isinstance(payload, dict) and isinstance(payload.get("events"), list):
                for ev in payload["events"]:
                    # Clone to avoid mutating the original
                    ev_copy = deepcopy(ev)
                    # Attach server-side timestamp and source endpoint for convenience
                    ev_copy["_received_at"] = entry.get("timestamp")
                    ev_copy["_source_endpoint"] = entry.get("endpoint")
                    flattened.append(ev_copy)
    return {"events": flattened}


@app.post("/clear")
async def clear_logs():
    with LOG_LOCK:
        REQUEST_LOG.clear()
    return RedirectResponse(url="/", status_code=303)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def catch_all(request: Request, full_path: str):
    data: Any = None
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            data = await request.json()
        except Exception as e:
            data = {"_error": "Invalid or no JSON body", "detail": str(e)}

    entry = {
        "timestamp": now_ist_str(),
        "endpoint": "/" + full_path,
        "method": request.method,
        "json": data,
    }

    if full_path not in ("", "clear"):
        with LOG_LOCK:
            REQUEST_LOG.append(entry)

    return JSONResponse({
        "status": "ok",
        "received": {
            "endpoint": entry["endpoint"],
            "method": entry["method"],
        },
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 18001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
