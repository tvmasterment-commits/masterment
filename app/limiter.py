from collections import defaultdict, deque
from math import ceil
from threading import Lock
from time import monotonic

_hits = defaultdict(deque)
_lock = Lock()

def check_rate_limit(key, limit, window):
    """Process-local fixed-window limiter. Returns retry seconds, or None."""
    now = monotonic()
    cutoff = now - window
    with _lock:
        bucket = _hits[key]
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return max(1, ceil(window - (now - bucket[0])))
        bucket.append(now)
        # Discard idle IPs so the small in-memory limiter cannot grow without bound.
        if len(_hits) > 4096:
            for ip in list(_hits):
                while _hits[ip] and _hits[ip][0] <= cutoff:
                    _hits[ip].popleft()
                if not _hits[ip]:
                    del _hits[ip]
        return None
