from __future__ import annotations

import asyncio
from unittest import mock

import httpx

from tp.notify.evalex_notifier import send_notification
from tp.notify.notification_retry import NOTIFICATION_MAX_ATTEMPTS
from tp.notify.settings_types import EvalexCameraNotification


def _client(post):
    mock_client = mock.AsyncMock()
    mock_client.post = post
    mock_client.__aenter__ = mock.AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = mock.AsyncMock(return_value=None)
    return mock_client


def test_camera_retries_retryable_http_failure():
    async def _run():
        notif = EvalexCameraNotification(
            app="vizmux",
            serverAddress="http://localhost:8000",
            cameraIds=["cam-1"],
            action="enable",
        )
        request = httpx.Request("POST", "http://localhost:8000/api/cameras/cam-1/enabled")
        response = httpx.Response(502, request=request, text="bad gateway")
        client = _client(mock.AsyncMock(return_value=response))

        with (
            mock.patch("tp.notify.evalex_notifier.httpx.AsyncClient", return_value=client),
            mock.patch("tp.notify.notification_retry.asyncio.sleep", new_callable=mock.AsyncMock),
        ):
            result = await send_notification(notif, None)

        assert result["status"] == "error"
        assert "HTTP 502" in result["error"]
        assert client.post.call_count == NOTIFICATION_MAX_ATTEMPTS

    asyncio.run(_run())


def test_camera_succeeds_after_transport_error():
    async def _run():
        notif = EvalexCameraNotification(
            app="piyoai",
            serverAddress="localhost:8001",
            cameraIds=["cam a"],
            action="disable",
        )
        request = httpx.Request("POST", "http://localhost:8001/api/cameras/cam%20a/enabled")
        ok = httpx.Response(200, request=request, json={"enabled": False, "changed": True})
        client = _client(mock.AsyncMock(side_effect=[httpx.ConnectError("refused"), ok]))

        with (
            mock.patch("tp.notify.evalex_notifier.httpx.AsyncClient", return_value=client),
            mock.patch("tp.notify.notification_retry.asyncio.sleep", new_callable=mock.AsyncMock),
        ):
            result = await send_notification(notif, None)

        assert result["status"] == "ok"
        assert result["cameras"]["cam a"]["status"] == "ok"
        assert client.post.call_count == 2
        client.post.assert_called_with(
            "http://localhost:8001/api/cameras/cam%20a/enabled",
            json={"enabled": False},
        )

    asyncio.run(_run())


def test_camera_does_not_retry_client_error():
    async def _run():
        notif = EvalexCameraNotification(
            app="vizrec",
            serverAddress="http://localhost:8002",
            cameraIds=["cam-1"],
            action="enable",
        )
        request = httpx.Request("POST", "http://localhost:8002/api/cameras/cam-1/enabled")
        response = httpx.Response(400, request=request, text="bad request")
        client = _client(mock.AsyncMock(return_value=response))

        with mock.patch("tp.notify.evalex_notifier.httpx.AsyncClient", return_value=client):
            result = await send_notification(notif, None)

        assert result["status"] == "error"
        assert "HTTP 400" in result["error"]
        client.post.assert_called_once()

    asyncio.run(_run())
