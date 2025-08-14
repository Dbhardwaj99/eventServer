import threading
from typing import Any, Dict, List

# In-memory store and lock for thread-safety
REQUEST_LOG: List[Dict[str, Any]] = []
LOG_LOCK = threading.Lock()
