from datetime import datetime, timezone
import json
import html
import threading
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

# In-memory store and lock for thread-safety
REQUEST_LOG: List[Dict[str, Any]] = []
LOG_LOCK = threading.Lock()

app = FastAPI(title="Event Server", version="1.0.0")

# CORS support (open to all for demo purposes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        # Fallback: stringify unknown/invalid JSON payloads
        return json.dumps({"unserializable": str(data)}, indent=2)


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
async def index():
    # Build Tailwind-powered page with auto-refresh
    items_html: List[str] = []
    with LOG_LOCK:
        # Show newest first
        for item in reversed(REQUEST_LOG):
            ts = html.escape(item.get("timestamp", ""))
            endpoint = html.escape(item.get("endpoint", ""))
            method = html.escape(item.get("method", ""))
            json_block = html.escape(pretty_json(item.get("json")))

            card = f"""
            <div class=\"rounded-xl border border-slate-200 bg-white shadow-sm p-5 hover:shadow-md transition\">
                <div class=\"flex items-center justify-between mb-2\">
                    <div class=\"text-sm text-slate-500\">{ts}</div>
                    <span class=\"inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700\">{method}</span>
                </div>
                <div class=\"font-mono text-slate-800 text-sm break-all mb-3\">{endpoint}</div>
                <pre class=\"bg-slate-50 rounded-lg p-3 overflow-x-auto text-sm leading-snug\"><code>{json_block}</code></pre>
            </div>
            """
            items_html.append(card)

    body = "\n".join(items_html) if items_html else (
        "<div class=\"text-slate-500 text-center\">No requests received yet. Send a POST request to any endpoint.</div>"
    )

    html_page = f"""
    <!doctype html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Event Server</title>
        <script src=\"https://cdn.tailwindcss.com\"></script>
        <!-- Auto-refresh every 5 seconds -->
        <script>
            setInterval(() => {{ window.location.reload(); }}, 5000);
        </script>
    </head>
    <body class=\"bg-slate-100 min-h-screen\">
        <div class=\"max-w-4xl mx-auto p-6\">
            <header class=\"mb-6 flex items-center justify-between\">
                <h1 class=\"text-2xl font-bold text-slate-800\">Event Server</h1>
                <div class=\"text-sm text-slate-500\">Auto-refreshing every 5s</div>
            </header>
            <div class=\"space-y-4\">
                {body}
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html_page)


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def catch_all(request: Request, full_path: str):
    # Try to parse JSON body when available
    data: Any = None
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            data = await request.json()
        except Exception as e:
            data = {"_error": "Invalid or no JSON body", "detail": str(e)}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": "/" + full_path,
        "method": request.method,
        "json": data,
    }

    # Do not log the UI refresh calls to "/"
    if full_path != "":
        with LOG_LOCK:
            REQUEST_LOG.append(entry)

    # Respond with a simple acknowledgement
    return JSONResponse({
        "status": "ok",
        "received": {
            "endpoint": entry["endpoint"],
            "method": entry["method"],
        },
    })


if __name__ == "__main__":
    # Run the server with uvicorn when executed directly
    uvicorn.run("main:app", host="0.0.0.0", port=15402, reload=False)

