from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from .inference_types import InferenceResult
from .notification_retry import RetryOutcome, http_status_should_retry, retry_async
from .notification_utils import (
    apply_template,
    apply_url_template,
    enrich_template_dict,
    filter_fields,
    simple_notification_face_names,
)
from .settings_types import FolderConfig, HttpNotification

logger = logging.getLogger("taskplanner.notify..http_notify")


def _auth_type(notif: HttpNotification) -> str:
    return (getattr(notif, "authType", "none") or "none").strip().lower()


class HttpNotifier:
    """Per-camera HTTP GET/POST/PUT webhooks (JSON / raw string / image / both), with auth and custom headers."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client:
            return
        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_all(
        self,
        notifications: list[HttpNotification],
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        for n in notifications:
            await self.send_notification(n, result, folder, output_root, source_image_path)

    def _resolve_httpx_auth(self, notif: HttpNotification, result_dict: dict):
        at = _auth_type(notif)
        if at in ("none", "bearer"):
            return None
        if at == "basic":
            user = apply_template((notif.httpUsername or "").strip(), result_dict)
            pw = apply_template(notif.httpPassword or "", result_dict)
            return (user, pw)
        if at == "digest":
            user = apply_template((notif.httpUsername or "").strip(), result_dict)
            pw = apply_template(notif.httpPassword or "", result_dict)
            return httpx.DigestAuth(user, pw)
        return None

    def _merge_headers(
        self,
        notif: HttpNotification,
        result_dict: dict,
        body_content_type: str | None,
    ) -> dict[str, str]:
        """Merge: custom headers, optional body Content-Type, then Bearer Authorization."""
        headers: dict[str, str] = {}
        extras = getattr(notif, "httpExtraHeaders", None) or []
        for h in extras:
            name = (h.name or "").strip()
            if not name:
                continue
            headers[name] = apply_template(h.value or "", result_dict)
        if body_content_type:
            headers["Content-Type"] = body_content_type
        if _auth_type(notif) == "bearer":
            tok = apply_template((notif.httpBearerToken or "").strip(), result_dict)
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        return headers

    def _http_outcome(self, resp: httpx.Response, verb: str, url: str) -> RetryOutcome:
        if resp.is_success:
            return RetryOutcome.OK
        if http_status_should_retry(resp.status_code):
            logger.warning(
                "HTTP %s %s retryable response: %s %s",
                verb,
                url,
                resp.status_code,
                (resp.text or "")[:200],
            )
            return RetryOutcome.RETRY
        if resp.status_code < 400:
            logger.warning(
                "HTTP %s %s unexpected non-success status %s",
                verb,
                url,
                resp.status_code,
            )
            return RetryOutcome.ABORT
        self._log_bad_status(resp, verb, url)
        return RetryOutcome.ABORT

    async def send_notification(
        self,
        notif: HttpNotification,
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        if not notif.enabled or not notif.url.strip() or not self._client:
            return

        url = notif.url.strip()
        method = (notif.method or "POST").strip().upper()
        if method not in ("GET", "POST", "PUT"):
            return

        result_dict = enrich_template_dict(
            result.to_dict(), folder, output_root, "http", source_image_path,
        )
        auth = self._resolve_httpx_auth(notif, result_dict)
        label = (notif.name or "").strip() or notif.id
        op_id = f"http {folder.friendlyName} {label}"

        async def run_once() -> RetryOutcome:
            if method == "GET":
                if notif.payload in ("image", "both"):
                    return RetryOutcome.OK
                resolved_url = self._build_get_url(url, getattr(notif, "getQueryTemplate", ""), result_dict)
                hdrs = self._merge_headers(notif, result_dict, None)
                resp = await self._client.get(
                    resolved_url,
                    auth=auth,
                    headers=hdrs if hdrs else None,
                )
                return self._http_outcome(resp, "GET", resolved_url)

            if method not in ("POST", "PUT"):
                return RetryOutcome.ABORT

            payload_type = notif.payload
            if payload_type == "json":
                text = self._format_text(notif, result_dict)
                enc = (getattr(notif, "httpBodyEncoding", "json") or "json").strip().lower()
                if enc == "raw":
                    ct = (getattr(notif, "httpContentType", "") or "text/plain; charset=utf-8").strip()
                    hdrs = self._merge_headers(notif, result_dict, ct)
                    resp = await self._client.request(
                        method,
                        url,
                        auth=auth,
                        headers=hdrs,
                        content=text.encode("utf-8"),
                    )
                    return self._http_outcome(resp, method, url)
                return await self._send_json_body(method, url, text, auth, notif, result_dict)
            if payload_type == "image":
                if result.annotated_image_path:
                    return await self._send_image_only(
                        method, url, result.annotated_image_path, auth, notif, result_dict,
                    )
                return RetryOutcome.OK
            if payload_type == "both":
                text = self._format_text(notif, result_dict)
                if result.annotated_image_path:
                    return await self._send_image_with_payload(
                        method, url, result.annotated_image_path, text, auth, notif, result_dict,
                    )
                return await self._send_json_body(method, url, text, auth, notif, result_dict)
            return RetryOutcome.ABORT

        await retry_async(op_id, run_once)

    def _format_text(self, notif: HttpNotification, result_dict: dict) -> str:
        if notif.messageMode == "simple":
            objects = list(dict.fromkeys(
                d["class"] for d in sorted(
                    result_dict.get("detections", []),
                    key=lambda d: d.get("confidence", 0),
                    reverse=True,
                )
            ))
            return json.dumps({"objects": objects, "faces": simple_notification_face_names(result_dict)})
        if notif.messageMode == "template" and notif.template:
            return apply_template(notif.template, result_dict)
        filtered = filter_fields(result_dict, notif.jsonFields)
        return json.dumps(filtered, indent=2)

    def _build_get_url(self, base_url: str, query_template: str, result_dict: dict) -> str:
        resolved_url = apply_url_template(base_url.strip(), result_dict)
        extra_query = apply_url_template((query_template or "").strip(), result_dict)
        extra_query = extra_query.lstrip("?&")
        if not extra_query:
            return resolved_url

        if "?" not in resolved_url:
            return f"{resolved_url}?{extra_query}"
        if resolved_url.endswith("?") or resolved_url.endswith("&"):
            return f"{resolved_url}{extra_query}"
        return f"{resolved_url}&{extra_query}"

    async def _send_json_body(
        self,
        method: str,
        url: str,
        text: str,
        auth,
        notif: HttpNotification,
        result_dict: dict,
    ) -> RetryOutcome:
        hdrs = self._merge_headers(notif, result_dict, None)
        kw: dict = {"auth": auth}
        if hdrs:
            kw["headers"] = hdrs
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            resp = await self._client.request(method, url, **kw, json={"message": text})  # type: ignore[union-attr]
        else:
            if isinstance(parsed, (dict, list)):
                resp = await self._client.request(method, url, **kw, json=parsed)  # type: ignore[union-attr]
            else:
                resp = await self._client.request(method, url, **kw, json={"message": parsed})  # type: ignore[union-attr]
        return self._http_outcome(resp, method, url)

    async def _send_image_only(
        self,
        method: str,
        url: str,
        photo_path: str,
        auth,
        notif: HttpNotification,
        result_dict: dict,
    ) -> RetryOutcome:
        photo_file = Path(photo_path)
        if not photo_file.is_file():
            logger.error("Annotated image not found: %s", photo_path)
            return RetryOutcome.ABORT
        files = {"image": (photo_file.name, photo_file.read_bytes(), "image/jpeg")}
        hdrs = self._merge_headers(notif, result_dict, None)
        kw: dict = {"auth": auth, "files": files}
        if hdrs:
            kw["headers"] = hdrs
        resp = await self._client.request(method, url, **kw)  # type: ignore[union-attr]
        return self._http_outcome(resp, method, url)

    async def _send_image_with_payload(
        self,
        method: str,
        url: str,
        photo_path: str,
        text: str,
        auth,
        notif: HttpNotification,
        result_dict: dict,
    ) -> RetryOutcome:
        photo_file = Path(photo_path)
        if not photo_file.is_file():
            logger.error("Annotated image not found: %s", photo_path)
            return await self._send_json_body(method, url, text, auth, notif, result_dict)
        enc = (getattr(notif, "httpBodyEncoding", "json") or "json").strip().lower()
        payload_slice = text[:8192]
        payload_bytes = payload_slice.encode("utf-8")
        if enc == "raw":
            part_ct = (getattr(notif, "httpContentType", "") or "text/plain; charset=utf-8").strip()
        else:
            part_ct = "application/json; charset=utf-8"
        files = {
            "payload": (None, payload_bytes, part_ct),
            "image": (photo_file.name, photo_file.read_bytes(), "image/jpeg"),
        }
        hdrs = self._merge_headers(notif, result_dict, None)
        kw: dict = {"auth": auth, "files": files}
        if hdrs:
            kw["headers"] = hdrs
        resp = await self._client.request(method, url, **kw)  # type: ignore[union-attr]
        return self._http_outcome(resp, method, url)

    def _log_bad_status(self, resp: httpx.Response, verb: str, url: str) -> None:
        if resp.status_code >= 400:
            logger.error(
                "HTTP %s %s failed: %s %s",
                verb,
                url,
                resp.status_code,
                (resp.text or "")[:200],
            )
