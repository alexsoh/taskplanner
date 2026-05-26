"""Tests for MQTT profile enable/disable listener."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

import pytest

from tp.notify.mqtt_client import MqttClient


@pytest.fixture
def client() -> MqttClient:
    return MqttClient()


class TestMqttProfileListener:
    def test_enable_invokes_callback_when_loop_set(self, client: MqttClient) -> None:
        profile_id = str(uuid.uuid4())
        callback = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            client.set_profile_callbacks(callback)
            client.set_event_loop(loop)
            client._handle_profile_command_message(f"{profile_id}/cmd/enable")
            loop.run_until_complete(asyncio.sleep(0))
            callback.assert_called_once_with(profile_id, True)
        finally:
            loop.close()

    def test_disable_invokes_callback_when_loop_set(self, client: MqttClient) -> None:
        profile_id = str(uuid.uuid4())
        callback = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            client.set_profile_callbacks(callback)
            client.set_event_loop(loop)
            client._handle_profile_command_message(f"{profile_id}/cmd/disable")
            loop.run_until_complete(asyncio.sleep(0))
            callback.assert_called_once_with(profile_id, False)
        finally:
            loop.close()

    def test_without_loop_callback_not_invoked(self, client: MqttClient) -> None:
        profile_id = str(uuid.uuid4())
        callback = MagicMock()
        client.set_profile_callbacks(callback)
        client._handle_profile_command_message(f"{profile_id}/cmd/enable")
        callback.assert_not_called()

    def test_invalid_topic_ignored(self, client: MqttClient) -> None:
        callback = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            client.set_profile_callbacks(callback)
            client.set_event_loop(loop)
            client._handle_profile_command_message("bad/topic")
            loop.run_until_complete(asyncio.sleep(0))
            callback.assert_not_called()
        finally:
            loop.close()

    def test_unknown_action_ignored(self, client: MqttClient) -> None:
        profile_id = str(uuid.uuid4())
        callback = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            client.set_profile_callbacks(callback)
            client.set_event_loop(loop)
            client._handle_profile_command_message(f"{profile_id}/cmd/pause")
            loop.run_until_complete(asyncio.sleep(0))
            callback.assert_not_called()
        finally:
            loop.close()

    def test_action_case_insensitive(self, client: MqttClient) -> None:
        profile_id = str(uuid.uuid4())
        callback = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            client.set_profile_callbacks(callback)
            client.set_event_loop(loop)
            client._handle_profile_command_message(f"{profile_id}/cmd/Enable")
            loop.run_until_complete(asyncio.sleep(0))
            callback.assert_called_once_with(profile_id, True)
        finally:
            loop.close()

    def test_configure_notifiers_reapplies_stored_loop(self) -> None:
        from tp.action_runner import configure_notifiers, mqtt, set_notifier_event_loop
        from tp.notify.settings_types import MqttSettings, TelegramSettings

        loop = asyncio.new_event_loop()
        callback = MagicMock()
        try:
            set_notifier_event_loop(loop)
            mqtt.set_profile_callbacks(callback)
            configure_notifiers(
                MqttSettings(enabled=False),
                TelegramSettings(),
            )
            assert mqtt._loop is loop
        finally:
            loop.close()
