from datetime import datetime, timezone
import json
import html
import threading
from typing import Any, Dict, List
import os
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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


def now_ist_str() -> str:
    """Return current time in IST as HH:MM:SS:MS (milliseconds)."""
    ist = ZoneInfo("Asia/Kolkata")
    dt = datetime.now(tz=ist)
    ms = f"{int(dt.microsecond / 1000):03d}"
    return dt.strftime("%H:%M:%S:") + ms


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
            <div class=\"rounded-xl border border-slate-800 bg-white/80 shadow-[4px_4px_0_#0f172a] p-5 hover:shadow-[3px_3px_0_#0f172a] transition\"> 
                <div class=\"flex items-center justify-between mb-2\"> 
                    <div class=\"retro-mono text-base text-slate-700\">{ts} IST</div> 
                    <span class=\"inline-flex items-center rounded bg-emerald-200 px-2 py-0.5 text-xs font-semibold text-slate-900 border border-slate-800\">{method}</span> 
                </div> 
                <div class=\"retro-mono text-lg text-slate-900 break-all mb-3\">{endpoint}</div> 
                <pre class=\"retro-mono bg-slate-50 rounded-lg p-3 overflow-x-hidden whitespace-pre-wrap break-words text-[15px] leading-5 border border-slate-300\"><code>{json_block}</code></pre> 
            </div> 
            """
            items_html.append(card)

    body = "\n".join(items_html) if items_html else (
        '<div class="retro-mono text-slate-700 text-center text-lg py-16">No requests yet. Send a POST request to any endpoint.</div>'
    )

    html_page = f"""
    <!doctype html>
    <html lang=\"en\">
    <head>
        <meta charset=\"utf-8\" />
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
        <title>Event Server</title>
        <script src=\"https://cdn.tailwindcss.com\"></script>
        <link href=\"https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap\" rel=\"stylesheet\">
        <style>
          .retro-title { font-family: 'Press Start 2P', system-ui, sans-serif; }
          .retro-mono { font-family: 'VT323', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
        </style>
        <!-- Auto-refresh every 5 seconds -->
        <script>
            setInterval(() => { window.location.reload(); }, 5000);
        </script>
    </head>
    <body class=\"min-h-screen bg-gradient-to-br from-amber-100 via-rose-100 to-sky-100\">
        <div class=\"max-w-5xl mx-auto p-6\">
            <header class=\"mb-6 flex items-center justify-between\"> 
                <div class=\"flex items-center gap-3\"> 
                    <div class=\"h-8 w-8 rounded-sm bg-gradient-to-br from-rose-400 to-orange-300 shadow-inner border border-black/20\"></div> 
                    <h1 class=\"retro-title text-lg md:text-2xl text-slate-900 drop-shadow-[1px_1px_0_rgba(0,0,0,0.2)]\">Event Server</h1> 
                </div> 
                <div class=\"flex items-center gap-3\"> 
                    <span class=\"retro-mono text-sm text-slate-700 bg-white/60 rounded px-2 py-1 border border-black/10\">Auto-refresh: 5s</span> 
                    <form method=\"post\" action=\"/clear\" onsubmit=\"return confirm('Clear all logs?');\"> 
                        <button type=\"submit\" class=\"retro-mono text-sm px-3 py-1 rounded border border-slate-800 bg-amber-200 hover:bg-amber-300 active:translate-y-[1px] shadow-[2px_2px_0_#0f172a] hover:shadow-[1px_1px_0_#0f172a] transition\">CLEAR</button> 
                    </form> 
                </div> 
            </header>
            <div class=\"space-y-4\">
                {body}
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html_page)


@app.post("/clear")
async def clear_logs():
    with LOG_LOCK:
        REQUEST_LOG.clear()
    return RedirectResponse(url="/", status_code=303)


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
        "timestamp": now_ist_str(),
        "endpoint": "/" + full_path,
        "method": request.method,
        "json": data,
    }

    # Do not log the UI refresh calls to "/" or clear actions
    if full_path not in ("", "clear"):
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
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
