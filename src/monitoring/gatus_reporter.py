from __future__ import annotations

import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

GATUS_REQUEST_TIMEOUT = 10


class GatusReporter:
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token

    def _build_report_url(
        self, client_name: str, success: bool, error: str | None
    ) -> str:
        query_params = f"success={success}"
        if error:
            query_params += f"&error={urllib.parse.quote(error)}"
        return f"{self.url}?{query_params}"

    def _send_request(self, url: str) -> None:
        request = urllib.request.Request(url, method="POST")
        request.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(request, timeout=GATUS_REQUEST_TIMEOUT) as response:
            logger.debug(f"Gatus health check updated: {response.status}")

    def report(self, client_name: str, success: bool, error: str | None = None) -> None:
        url = self._build_report_url(client_name, success, error)
        try:
            self._send_request(url)
        except Exception as exc:
            logger.warning(f"Gatus report failed for {client_name}: {exc}")
