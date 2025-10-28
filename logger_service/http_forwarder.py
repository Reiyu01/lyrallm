import asyncio
import logging
import json
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False


def _sanitize_payload(value: Any) -> Any:
    """Recursively convert non-JSON-serializable types (e.g., datetime) into strings."""
    if isinstance(value, dict):
        return {k: _sanitize_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_payload(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


async def post_json(url: str, payload: dict, timeout: float = 5.0) -> bool:
    """Post JSON payload to URL with simple retry/backoff. Returns True on success."""
    if not HAS_HTTPX:
        logger.warning("httpx not installed; skipping HTTP forward to %s", url)
        return False

    max_attempts = 3
    backoff = 0.5
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, max_attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                sanitized = _sanitize_payload(payload)
                r = await client.post(url, json=sanitized, headers=headers)
                if 200 <= r.status_code < 300:
                    logger.debug("HTTP forward success to %s (status=%d)", url, r.status_code)
                    return True
                else:
                    logger.warning("HTTP forward to %s returned status=%d: %s", url, r.status_code, r.text)
        except Exception as e:
            logger.warning("HTTP forward attempt %d to %s failed: %s", attempt, url, e)

        # backoff before next try
        await asyncio.sleep(backoff)
        backoff *= 2

    logger.error("HTTP forward to %s failed after %d attempts", url, max_attempts)
    return False


async def post_udp(host: str, port: int, payload: dict) -> bool:
    """Send payload as a UDP datagram (JSON encoded). Returns True if send succeeded.

    Note: UDP is connectionless and unreliable; this function performs a best-effort send.
    """
    try:
        sanitized = _sanitize_payload(payload)
        data = json.dumps(sanitized).encode('utf-8')
    except Exception as e:
        logger.warning("Failed to serialize payload for UDP: %s", e)
        return False

    loop = asyncio.get_event_loop()

    def _send():
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(True)
            sock.sendto(data, (host, int(port)))
            sock.close()
            return True
        except Exception as e:
            # local blocking send error
            logger.warning("UDP sendto failed: %s", e)
            try:
                sock.close()
            except Exception:
                pass
            return False

    try:
        return await loop.run_in_executor(None, _send)
    except Exception as e:
        logger.warning("UDP send failed in executor: %s", e)
        return False
