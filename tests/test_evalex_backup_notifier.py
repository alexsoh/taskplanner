from __future__ import annotations

import asyncio
from unittest import mock

import httpx

from tp.notify.evalex_backup_notifier import send_notification
from tp.notify.settings_types import EvalexBackupNotification


def test_backup_calls_settings_backup_with_retain_param():
    async def _run():
        notif = EvalexBackupNotification(
            app="vizmux",
            serverAddress="http://localhost:8000",
            retentionDays=14,
        )

        mock_response = mock.MagicMock()
        mock_response.json.return_value = {"status": "ok", "backup_file": "settings_20260101.json"}
        mock_response.raise_for_status = mock.MagicMock()

        mock_client = mock.AsyncMock()
        mock_client.post = mock.AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=None)

        with mock.patch("tp.notify.evalex_backup_notifier.httpx.AsyncClient", return_value=mock_client):
            result = await send_notification(notif, None)

        assert result["status"] == "ok"
        assert result["retentionDays"] == 14
        mock_client.post.assert_called_once_with(
            "http://localhost:8000/api/settings/backup",
            params={"retain": 14},
        )

    asyncio.run(_run())


def test_backup_returns_error_on_http_failure():
    async def _run():
        notif = EvalexBackupNotification(
            app="piyoai",
            serverAddress="localhost:8001",
            retentionDays=7,
        )

        request = httpx.Request("POST", "http://localhost:8001/api/settings/backup")
        response = httpx.Response(500, request=request, text="Internal Server Error")

        mock_client = mock.AsyncMock()
        mock_client.post = mock.AsyncMock(side_effect=httpx.HTTPStatusError("error", request=request, response=response))
        mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mock.AsyncMock(return_value=None)

        with mock.patch("tp.notify.evalex_backup_notifier.httpx.AsyncClient", return_value=mock_client):
            result = await send_notification(notif, None)

        assert result["status"] == "error"
        assert "HTTP 500" in result["error"]

    asyncio.run(_run())


def test_backup_skips_when_disabled():
    async def _run():
        notif = EvalexBackupNotification(enabled=False)
        result = await send_notification(notif, None)
        assert result["status"] == "skipped"

    asyncio.run(_run())
