import json
import urllib.error
import urllib.request
from typing import Any, Dict

from .base import ProviderError


def post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 90) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError("provider HTTP %s: %s" % (exc.code, body[:600])) from exc
    except urllib.error.URLError as exc:
        raise ProviderError("provider request failed: %s" % exc.reason) from exc
