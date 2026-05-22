from __future__ import annotations

import logging
import re
import ssl
from urllib.parse import quote, urlparse

import httpx

from .inference_types import InferenceResult
from .notification_retry import RetryOutcome, http_status_should_retry, retry_async
from .notification_utils import apply_template, enrich_template_dict
from .settings_types import FolderConfig, NvrNotification

logger = logging.getLogger("taskplanner.notify..nvr_notify")

# Redact `pw=` query value for logs (Blue Iris legacy fallback puts credentials in the URL).
_PW_QUERY_RE = re.compile(r"([?&])pw=[^&]*")

_INSECURE_SSL = ssl.create_default_context()
_INSECURE_SSL.check_hostname = False
_INSECURE_SSL.verify_mode = ssl.CERT_NONE


def _origin_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid base URL")
    return f"{parsed.scheme}://{parsed.netloc}"


def _coerce_int(val: object, default: int = 0) -> int:
    try:
        return int(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _redact_pw_query(url: str) -> str:
    return _PW_QUERY_RE.sub(r"\1pw=***", url)


def _nvr_folder_label(folder: FolderConfig) -> str:
    """Human-readable camera label for NVR logs (friendly name)."""
    return (folder.friendlyName or "").strip() or "(unnamed camera)"


def _log_one_line(text: str, max_len: int = 200) -> str:
    """Collapse whitespace for a single log line."""
    s = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s


def _blueiris_camera_trigger_query(
    cam_q: str,
    notif: NvrNotification,
    folder: FolderConfig,
    result: InferenceResult | None,
    output_root: str,
    source_image_path: str | None,
) -> str:
    """Return query string after ``camera=`` (no leading ``?``): ``trigger`` (no value) ``&flagalert=1`` plus optional ``memo=``."""
    base_q = f"camera={cam_q}&trigger&flagalert=1"
    tmpl = str(getattr(notif, "blueIrisMemoTemplate", "") or "").strip()
    if not tmpl or result is None:
        return base_q
    rd = enrich_template_dict(
        result.to_dict(),
        folder,
        output_root or "",
        "nvr",
        source_image_path,
    )
    raw = apply_template(tmpl, rd).strip()
    if not raw:
        return base_q
    return f"{base_q}&memo={quote(raw, safe='')}"


class NvrNotifier:
    """Trigger NVR/camera recording via vendor HTTP APIs (Dahua, Hikvision, Reolink, EZVIZ, Blue Iris)."""

    _CLIENT_TIMEOUT = 30.0

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client:
            return
        self._client = httpx.AsyncClient(
            timeout=self._CLIENT_TIMEOUT,
            follow_redirects=True,
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_all(
        self,
        notifications: list[NvrNotification],
        folder: FolderConfig,
        result: InferenceResult | None = None,
        output_root: str = "",
        source_image_path: str | None = None,
    ) -> None:
        for n in notifications:
            await self.send_notification(
                n,
                folder,
                result=result,
                output_root=output_root,
                source_image_path=source_image_path,
            )

    async def send_notification(
        self,
        notif: NvrNotification,
        folder: FolderConfig,
        result: InferenceResult | None = None,
        output_root: str = "",
        source_image_path: str | None = None,
    ) -> None:
        if not notif.enabled:
            return
        base = (notif.baseUrl or "").strip()
        if not base:
            return
        try:
            origin = _origin_url(base)
        except ValueError:
            logger.error("NVR %s: invalid base URL for %s", notif.brand, _nvr_folder_label(folder))
            return
        brand = (notif.brand or "reolink").strip().lower()
        verify_ssl = notif.verifySsl
        use_tls = urlparse(origin).scheme.lower() == "https"
        insecure_verify: bool | ssl.SSLContext = _INSECURE_SSL if use_tls else False
        shared = self._client
        if verify_ssl and not shared:
            return

        async def _dispatch(client: httpx.AsyncClient) -> RetryOutcome:
            if brand == "reolink":
                return await self._send_reolink(client, origin, notif)
            if brand in ("hikvision", "ezviz"):
                return await self._send_hikvision(client, origin, notif)
            if brand == "dahua":
                return await self._send_dahua(client, origin, notif)
            if brand == "blueiris":
                return await self._send_blueiris(
                    client,
                    origin,
                    notif,
                    folder,
                    result,
                    output_root,
                    source_image_path,
                )
            logger.warning("NVR unknown brand %s", brand)
            return RetryOutcome.ABORT

        row_label = (getattr(notif, "name", "") or "").strip() or notif.id
        op_id = f"nvr {brand} {_nvr_folder_label(folder)} {row_label}"

        async def run_once() -> RetryOutcome:
            if verify_ssl:
                if shared is None:
                    return RetryOutcome.ABORT
                return await _dispatch(shared)
            async with httpx.AsyncClient(
                timeout=self._CLIENT_TIMEOUT,
                follow_redirects=True,
                verify=insecure_verify,
            ) as scoped:
                return await _dispatch(scoped)

        await retry_async(op_id, run_once)

    async def _send_reolink(
        self, client: httpx.AsyncClient, origin: str, notif: NvrNotification
    ) -> RetryOutcome:
        user = quote((notif.httpUsername or "").strip(), safe="")
        pw = quote(notif.httpPassword or "", safe="")
        channel = _coerce_int(notif.channel, 0)
        use_v20 = bool(getattr(notif, "reolinkUseV20Api", False))

        async def _post_outcome(cmd: str, param: dict) -> RetryOutcome:
            path = f"/cgi-bin/api.cgi?user={user}&password={pw}&cmd={cmd}"
            url = f"{origin.rstrip('/')}{path}"
            body = [{"cmd": cmd, "action": 0, "param": param}]
            try:
                resp = await client.post(url, json=body)
            except httpx.RequestError:
                return RetryOutcome.RETRY
            if not resp.is_success:
                if http_status_should_retry(resp.status_code):
                    logger.warning("Reolink %s HTTP %s (retryable)", cmd, resp.status_code)
                    return RetryOutcome.RETRY
                logger.error(
                    "Reolink %s HTTP %s %s",
                    cmd,
                    resp.status_code,
                    (resp.text or "")[:200],
                )
                return RetryOutcome.ABORT
            try:
                data = resp.json()
            except (ValueError, TypeError) as e:
                logger.error("Reolink %s malformed JSON: %s", cmd, e)
                return RetryOutcome.ABORT
            if not data or not isinstance(data, list):
                logger.error("Reolink %s malformed response", cmd)
                return RetryOutcome.ABORT
            row = data[0]
            code = row.get("code", -1)
            if code != 0:
                logger.error(
                    "Reolink %s error %s: %s",
                    cmd,
                    code,
                    row.get("error", ""),
                )
                return RetryOutcome.ABORT
            return RetryOutcome.OK

        if use_v20:
            return await _post_outcome("SetRecV20", {"Rec": {"channel": channel, "enable": 1}})

        first = await _post_outcome("SetRec", {"Rec": {"channel": channel, "schedule": {"enable": 1}}})
        if first == RetryOutcome.OK:
            return RetryOutcome.OK
        if first == RetryOutcome.RETRY:
            return RetryOutcome.RETRY
        logger.debug("Reolink SetRec failed, trying SetRecV20")
        return await _post_outcome("SetRecV20", {"Rec": {"channel": channel, "enable": 1}})

    async def _send_hikvision(self, client: httpx.AsyncClient, origin: str, notif: NvrNotification) -> RetryOutcome:
        tid = _coerce_int(getattr(notif, "hikvisionTrackId", 0), 0)
        if tid <= 0:
            # 0-based stream index: first ISAPI track is typically 101
            tid = 101 + _coerce_int(notif.channel, 0)
        path = f"/ISAPI/ContentMgmt/record/tracks/{tid}/start"
        url = f"{origin.rstrip('/')}{path}"
        auth = httpx.DigestAuth(
            (notif.httpUsername or "").strip(),
            notif.httpPassword or "",
        )
        try:
            resp = await client.put(url, auth=auth)
        except httpx.RequestError:
            return RetryOutcome.RETRY
        if resp.is_success:
            return RetryOutcome.OK
        if http_status_should_retry(resp.status_code):
            logger.warning(
                "ISAPI recording PUT %s retryable: %s %s",
                path,
                resp.status_code,
                (resp.text or "")[:200],
            )
            return RetryOutcome.RETRY
        logger.error(
            "ISAPI recording PUT %s failed: %s %s",
            path,
            resp.status_code,
            (resp.text or "")[:200],
        )
        return RetryOutcome.ABORT

    async def _send_dahua(self, client: httpx.AsyncClient, origin: str, notif: NvrNotification) -> RetryOutcome:
        ch = _coerce_int(notif.channel, 0)
        path = f"/cgi-bin/recordManager.cgi?action=startRecord&channel={ch}"
        url = f"{origin.rstrip('/')}{path}"
        auth = httpx.DigestAuth(
            (notif.httpUsername or "").strip(),
            notif.httpPassword or "",
        )
        try:
            resp = await client.get(url, auth=auth)
        except httpx.RequestError:
            return RetryOutcome.RETRY
        if resp.is_success:
            return RetryOutcome.OK
        if http_status_should_retry(resp.status_code):
            logger.warning(
                "Dahua NVR GET %s retryable: %s %s",
                path,
                resp.status_code,
                (resp.text or "")[:200],
            )
            return RetryOutcome.RETRY
        logger.error(
            "Dahua NVR GET %s failed: %s %s",
            path,
            resp.status_code,
            (resp.text or "")[:200],
        )
        return RetryOutcome.ABORT

    async def _send_blueiris(
        self,
        client: httpx.AsyncClient,
        origin: str,
        notif: NvrNotification,
        folder: FolderConfig,
        result: InferenceResult | None,
        output_root: str,
        source_image_path: str | None,
    ) -> RetryOutcome:
        """Fire Blue Iris camera trigger via GET ``/admin?camera=...&trigger&flagalert=1`` (optional ``memo=``).

        If **both** username and password are set on this NVR row, the first request uses **HTTP Basic**
        auth on that URL (no ``user``/``pw`` in the query). If BI returns **401**, retries once with
        legacy ``user``/``pw`` query parameters. If either credential field is empty, sends a single
        **anonymous** request (no ``Authorization``, no query login).
        """
        short = (getattr(notif, "blueIrisCameraShortName", "") or "").strip()
        if not short:
            short = (folder.friendlyName or "").strip()
        if not short:
            label = _nvr_folder_label(folder)
            logger.error(
                "NVR blueiris failed for %s: no camera identifier "
                "(Blue Iris short name override is empty and camera name is empty)",
                label,
            )
            return RetryOutcome.ABORT
        user = (notif.httpUsername or "").strip()
        pw_raw = notif.httpPassword or ""
        have_creds = bool(user) and bool(pw_raw.strip())
        cam_q = quote(short, safe="")
        q_body = _blueiris_camera_trigger_query(cam_q, notif, folder, result, output_root, source_image_path)
        path_basic = f"/admin?{q_body}"
        url_basic = f"{origin.rstrip('/')}{path_basic}"

        used_legacy_query_auth = False
        try:
            if have_creds:
                resp = await client.get(
                    url_basic,
                    auth=httpx.BasicAuth(user, pw_raw),
                )
                auth_mode = "HTTP Basic auth"
                safe_url = url_basic
                if resp.status_code == 401:
                    q_legacy = (
                        f"{q_body}&user={quote(user, safe='')}&pw={quote(pw_raw, safe='')}"
                    )
                    path_legacy = f"/admin?{q_legacy}"
                    url_legacy = f"{origin.rstrip('/')}{path_legacy}"
                    logger.debug("Blue Iris trigger Basic 401; retrying with query-string credentials")
                    resp = await client.get(url_legacy)
                    safe_url = _redact_pw_query(url_legacy)
                    used_legacy_query_auth = True
                    auth_mode = "legacy query user/pw"
            else:
                resp = await client.get(url_basic)
                safe_url = url_basic
                auth_mode = "no credentials (anonymous)"
        except httpx.RequestError:
            return RetryOutcome.RETRY

        snippet = (resp.text or "")[:300]
        label = _nvr_folder_label(folder)
        if resp.status_code >= 400:
            if http_status_should_retry(resp.status_code):
                logger.warning(
                    "NVR blueiris retryable HTTP %s for %s via %s",
                    resp.status_code,
                    label,
                    auth_mode,
                )
                return RetryOutcome.RETRY
            hint = ""
            if resp.status_code == 401:
                if used_legacy_query_auth:
                    hint = (
                        " — HTTP Basic and query-string credentials were rejected "
                        "(wrong user/password or BI web server policy)"
                    )
                else:
                    hint = (
                        " — BI requires authentication (set username+password in this NVR row for Basic auth, "
                        "or allow this client IP without login in Blue Iris web server settings)"
                    )
            elif resp.status_code == 403:
                hint = " — BI denied access (forbidden for this user or client IP)"
            elif resp.status_code == 404:
                hint = " — wrong base URL or web server path (expected /admin on the BI web port)"
            logger.error(
                "NVR blueiris failed for %s: HTTP %s via %s; request=%s; response=%s%s",
                label,
                resp.status_code,
                auth_mode,
                safe_url,
                _log_one_line(snippet) or "(empty body)",
                hint,
            )
            return RetryOutcome.ABORT
        if "camera=null" in snippet.lower():
            logger.error(
                "NVR blueiris failed for %s: Blue Iris returned camera=NULL "
                "(the camera= value %r is not a recognized short name on this BI server); request=%s; response=%s",
                label,
                short,
                safe_url,
                _log_one_line(snippet) or "(empty body)",
            )
            return RetryOutcome.ABORT
        return RetryOutcome.OK
