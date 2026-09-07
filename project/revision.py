from __future__ import annotations

import os
import re

_REVISION = re.compile(r"^[0-9a-f]{40}$")


def deployed_revision() -> str | None:
    """Return the exact deployed candidate revision, or fail closed."""
    render_value = os.environ.get("RENDER_GIT_COMMIT")
    if render_value is not None:
        normalized = render_value.strip().lower()
        return normalized if _REVISION.fullmatch(normalized) else None
    local_value = os.environ.get("BRIDGEWRIGHT_TARGET_REVISION", "").strip().lower()
    return local_value if _REVISION.fullmatch(local_value) else None


class BridgewrightRevisionMiddleware:
    """Bind homepage and its assurance probes to the deployed candidate."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path == "/":
            revision = deployed_revision()
            if revision is not None:
                response["X-Bridgewright-Revision"] = revision
        return response
