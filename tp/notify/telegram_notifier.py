from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import httpx

from .inference_types import InferenceResult
from .notification_retry import RetryOutcome, http_status_should_retry, retry_async
from .notification_utils import apply_template, enrich_template_dict, filter_fields, simple_notification_face_names
from .settings_types import FolderConfig, TelegramNotification, TelegramSettings

logger = logging.getLogger("taskplanner.notify..telegram")

TELEGRAM_API = "https://api.telegram.org/bot{token}"


class TelegramNotifier:
    def __init__(self) -> None:
        self._token: str = ""
        self._client: httpx.AsyncClient | None = None
        self._chat_last_send: dict[str, float] = {}

    def configure(self, settings: TelegramSettings) -> None:
        self._token = settings.token if settings.enabled else ""
        if self._client:
            pass

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=30.0)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._chat_last_send.clear()

    async def send_notification(
        self,
        notif: TelegramNotification,
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        if not self._token or not notif.enabled or not notif.chatId:
            return
        if not self._client:
            return

        chat_id = notif.chatId
        now = time.monotonic()
        last = self._chat_last_send.get(chat_id, 0.0)
        wait = max(0.0, 1.0 - (now - last))
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            result_dict = enrich_template_dict(
                result.to_dict(), folder, output_root, "telegram", source_image_path,
            )
            base_url = TELEGRAM_API.format(token=self._token)
            payload_type = notif.payload
            label = (notif.name or "").strip() or notif.id
            op_base = f"telegram {folder.friendlyName} {label}"

            if payload_type == "json":
                text = self._format_text(notif, result_dict)

                async def run_msg() -> RetryOutcome:
                    return await self._send_message_once(base_url, chat_id, text)

                await retry_async(f"{op_base} sendMessage", run_msg)

            elif payload_type == "image":
                if result.annotated_image_path:
                    path = result.annotated_image_path

                    async def run_photo() -> RetryOutcome:
                        return await self._send_photo_once(base_url, chat_id, path)

                    await retry_async(f"{op_base} sendPhoto", run_photo)

            elif payload_type == "both":
                text = self._format_text(notif, result_dict)
                if result.annotated_image_path:
                    path = result.annotated_image_path

                    async def run_photo_cap() -> RetryOutcome:
                        return await self._send_photo_once(base_url, chat_id, path, caption=text)

                    await retry_async(f"{op_base} sendPhoto", run_photo_cap)
                else:

                    async def run_msg2() -> RetryOutcome:
                        return await self._send_message_once(base_url, chat_id, text)

                    await retry_async(f"{op_base} sendMessage", run_msg2)
        finally:
            # Rate-limit the next send from when this notification finishes (incl. retries), not
            # from before the first HTTP attempt — avoids bursting the API after a slow/failed run.
            self._chat_last_send[chat_id] = time.monotonic()

    async def send_all(
        self,
        notifications: list[TelegramNotification],
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        for notif in notifications:
            await self.send_notification(notif, result, folder, output_root, source_image_path)

    def _format_text(self, notif: TelegramNotification, result_dict: dict) -> str:
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

    def _telegram_response_outcome(self, resp: httpx.Response, context: str) -> RetryOutcome:
        if resp.status_code != 200:
            if http_status_should_retry(resp.status_code):
                logger.warning("Telegram %s retryable HTTP %s: %s", context, resp.status_code, resp.text[:200])
                return RetryOutcome.RETRY
            logger.error("Telegram %s failed: HTTP %s %s", context, resp.status_code, resp.text[:200])
            return RetryOutcome.ABORT
        try:
            data = resp.json()
        except (json.JSONDecodeError, TypeError, ValueError):
            return RetryOutcome.OK
        if not isinstance(data, dict):
            logger.warning("Telegram %s unexpected JSON shape: %r", context, data)
            return RetryOutcome.ABORT
        if data.get("ok") is True:
            return RetryOutcome.OK
        err_code = data.get("error_code")
        if err_code == 429:
            logger.warning("Telegram %s rate limited: %s", context, data)
            return RetryOutcome.RETRY
        if isinstance(err_code, int) and err_code >= 500:
            logger.warning("Telegram %s server error in body: %s", context, data)
            return RetryOutcome.RETRY
        logger.error("Telegram %s API error: %s", context, data)
        return RetryOutcome.ABORT

    async def _send_message_once(self, base_url: str, chat_id: str, text: str) -> RetryOutcome:
        url = f"{base_url}/sendMessage"
        resp = await self._client.post(url, json={"chat_id": chat_id, "text": text})  # type: ignore[union-attr]
        return self._telegram_response_outcome(resp, "sendMessage")

    async def _send_photo_once(self, base_url: str, chat_id: str, photo_path: str, caption: str = "") -> RetryOutcome:
        url = f"{base_url}/sendPhoto"
        photo_file = Path(photo_path)
        if not photo_file.exists():
            logger.error("Annotated image not found: %s", photo_path)
            return RetryOutcome.ABORT

        data: dict[str, str] = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]

        files = {"photo": (photo_file.name, photo_file.read_bytes(), "image/jpeg")}
        resp = await self._client.post(url, data=data, files=files)  # type: ignore[union-attr]
        return self._telegram_response_outcome(resp, "sendPhoto")
