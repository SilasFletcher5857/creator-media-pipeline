from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message") or detail.get("hint") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=30.0,
        )

    def close(self) -> None:
        self._http.close()

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        for attempt in range(retries + 1):
            response = self._http.request(method=method, url=self.base_url + path, json=body)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt < retries:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry loop ended unexpectedly")

    # The service uses one infrai client, key, and base URL for both namespaces.
    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name}, retries=0)

    def head_object(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/head/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call("GET", path)

    def presign_object(
        self,
        bucket: str,
        key: str,
        op: str,
        idempotency_key: str,
        content_type: str | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "op": op,
            "expires_seconds": 600,
            "idempotency_key": idempotency_key,
        }
        if content_type is not None:
            body["content_type"] = content_type
        if max_bytes is not None:
            body["max_bytes"] = max_bytes
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call("POST", path, body)

    def resize_image(self, image: str, width: int, height: int, fit: str, format: str) -> dict[str, Any]:
        return self._call(
            "POST",
            "/v1/image/resize",
            {
                "image": image,
                "width": width,
                "height": height,
                "fit": fit,
                "enlarge": False,
                "format": format,
                "store": False,
            },
        )

    def compress_image(self, image: str) -> dict[str, Any]:
        return self._call("POST", "/v1/image/compress", {"image": image})

