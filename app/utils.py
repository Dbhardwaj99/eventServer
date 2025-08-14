import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any


def pretty_json(data: Any) -> str:
    try:
        return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        return json.dumps({"unserializable": str(data)}, indent=2)


def now_ist_str() -> str:
    ist = ZoneInfo("Asia/Kolkata")
    dt = datetime.now(tz=ist)
    ms = f"{int(dt.microsecond / 1000):03d}"
    return dt.strftime("%H:%M:%S:") + ms
