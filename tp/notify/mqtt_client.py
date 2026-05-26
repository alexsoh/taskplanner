from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from .settings_types import MqttSettings, MqttNotification, FolderConfig, APP_DIR, _parse_bool_setting
from .inference_types import InferenceResult
from .notification_utils import (
    apply_template,
    enrich_template_dict,
    filter_fields,
    simple_notification_face_names,
)

if TYPE_CHECKING:
    from typing import Awaitable

logger = logging.getLogger("taskplanner.notify..mqtt")

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False


class MqttClient:
    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._connected = False
        self._listener_enabled = False
        self._listener_topic_prefix = ""
        self._publish_qos = 1
        self._subscribe_qos = 1
        self._image_callback: Callable[[str, str], Awaitable[None]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cmd_listener_enabled = False
        self._cmd_listener_topic_prefix = ""
        self._cmd_pause: Callable[[list[str], int], list[str]] | None = None
        self._cmd_resume: Callable[[list[str]], list[str]] | None = None
        self._cmd_set_enabled: Callable[[list[str], bool], list[str]] | None = None
        self._cmd_resolve: Callable[[str], list[str]] | None = None
        self._profile_listener_enabled = False
        self._profile_listener_topic_prefix = ""
        self._profile_set_enabled: Callable[[str, bool], None] | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def set_image_callback(
        self,
        callback: Callable[[str, str], Awaitable[None]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._image_callback = callback
        self._loop = loop

    def set_profile_callbacks(self, set_enabled_fn: Callable[[str, bool], None]) -> None:
        self._profile_set_enabled = set_enabled_fn

    def set_command_callbacks(
        self,
        pause_fn: Callable[[list[str], int], list[str]],
        resume_fn: Callable[[list[str]], list[str]],
        set_enabled_fn: Callable[[list[str], bool], list[str]],
        resolve_fn: Callable[[str], list[str]],
    ) -> None:
        self._cmd_pause = pause_fn
        self._cmd_resume = resume_fn
        self._cmd_set_enabled = set_enabled_fn
        self._cmd_resolve = resolve_fn

    def connect(self, settings: MqttSettings) -> None:
        if not HAS_MQTT:
            logger.warning("paho-mqtt not installed, MQTT disabled")
            return
        if not settings.enabled or not settings.broker:
            return

        self.disconnect()
        self._listener_enabled = settings.listenerEnabled
        self._listener_topic_prefix = settings.listenerTopicPrefix.rstrip("/")
        self._publish_qos = max(0, min(2, int(settings.publishQos)))
        self._subscribe_qos = max(0, min(2, int(settings.subscribeQos)))
        self._cmd_listener_enabled = settings.commandListenerEnabled
        self._cmd_listener_topic_prefix = settings.commandListenerTopicPrefix.rstrip("/")
        self._profile_listener_enabled = settings.profileListenerEnabled
        self._profile_listener_topic_prefix = settings.profileListenerTopicPrefix.rstrip("/")

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if settings.username:
            self._client.username_pw_set(settings.username, settings.password)

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_connect_fail = self._on_connect_fail
        # Exponential backoff between reconnect attempts (paho defaults: 1s .. 120s).
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

        try:
            # Non-blocking connect so loop_start()'s threaded loop_forever(retry_first_connection=True)
            # can retry until the broker is reachable (blocking connect() would fail once and stop).
            self._client.connect_async(settings.broker, settings.port, keepalive=60)
            self._client.loop_start()
            logger.info("Connecting to MQTT broker %s:%d", settings.broker, settings.port)
        except Exception:
            logger.error("Failed to start MQTT client", exc_info=True)
            self._cleanup_failed_client()

    def _cleanup_failed_client(self) -> None:
        """Best-effort teardown when connect_async/loop_start fails before a healthy session."""
        client = self._client
        self._client = None
        self._connected = False
        if not client:
            return
        try:
            client.loop_stop()
        except Exception:
            logger.debug("loop_stop during MQTT cleanup", exc_info=True)
        try:
            client.disconnect()
        except Exception:
            logger.debug("disconnect during MQTT cleanup", exc_info=True)

    def _on_connect_fail(self, _client: mqtt.Client, _userdata: object) -> None:
        logger.warning("MQTT broker unreachable or connection failed (retrying in background)")

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _connect_flags: object,
        reason_code: object,
        _properties: object = None,
    ) -> None:
        # CallbackAPIVersion.VERSION2 passes ReasonCode; %d logging would raise TypeError.
        failed = reason_code.is_failure if hasattr(reason_code, "is_failure") else reason_code != 0
        if failed:
            self._connected = False
            logger.error("MQTT connection failed: %s", reason_code)
            return
        self._connected = True
        logger.info("Connected to MQTT broker")
        self._subscribe_listener(client)

    def _subscribe_listener(self, client: mqtt.Client | None = None) -> None:
        c = client or self._client
        if not c:
            return
        if self._listener_enabled and self._listener_topic_prefix:
            topic = f"{self._listener_topic_prefix}/+"
            c.subscribe(topic, qos=self._subscribe_qos)
            logger.info("Subscribed to MQTT listener topic: %s", topic)
        if self._cmd_listener_enabled and self._cmd_listener_topic_prefix:
            topic = f"{self._cmd_listener_topic_prefix}/+/cmd/+"
            c.subscribe(topic, qos=self._subscribe_qos)
            logger.info("Subscribed to MQTT command listener: %s", topic)
        if self._profile_listener_enabled and self._profile_listener_topic_prefix:
            topic = f"{self._profile_listener_topic_prefix}/+/cmd/+"
            c.subscribe(topic, qos=self._subscribe_qos)
            logger.info("Subscribed to MQTT profile listener: %s", topic)

    def _on_message(self, _client: mqtt.Client, _userdata: object, msg: mqtt.MQTTMessage) -> None:
        from ._stubs import IS_DEMO, demo_server_expired, grace_expired, activation_required
        if activation_required or grace_expired:
            return
        if IS_DEMO and demo_server_expired:
            return

        # Route to profile listener (prefix/profile_id/cmd/action)
        if self._profile_listener_enabled and self._profile_listener_topic_prefix:
            prof_prefix = self._profile_listener_topic_prefix + "/"
            if msg.topic.startswith(prof_prefix) and "/cmd/" in msg.topic:
                self._handle_profile_command_message(msg.topic[len(prof_prefix):])
                return

        # Route to command listener (prefix/camera_id/cmd/action)
        if self._cmd_listener_enabled and self._cmd_listener_topic_prefix:
            cmd_prefix = self._cmd_listener_topic_prefix + "/"
            if msg.topic.startswith(cmd_prefix) and "/cmd/" in msg.topic:
                self._handle_command_message(msg.topic[len(cmd_prefix):], msg.payload)
                return

        # Route to image listener
        if not self._listener_enabled or not self._image_callback or not self._loop:
            return

        prefix = self._listener_topic_prefix + "/"
        if not msg.topic.startswith(prefix):
            return

        camera_name = msg.topic[len(prefix):]
        if not camera_name or not msg.payload:
            return

        safe_name = camera_name.replace("/", "_").replace("\\", "_").replace("..", "_")
        temp_dir = APP_DIR / "temp"
        temp_dir.mkdir(exist_ok=True)
        temp_path = temp_dir / f"mqttlisten_{uuid.uuid4()}_{safe_name}.jpg"
        try:
            temp_path.write_bytes(msg.payload)
        except Exception:
            logger.error("Failed to write MQTT listener image to temp", exc_info=True)
            return

        logger.info("MQTT listener: received image for camera '%s' (%d bytes)", camera_name, len(msg.payload))
        asyncio.run_coroutine_threadsafe(
            self._image_callback(camera_name, str(temp_path)),
            self._loop,
        )

    def _handle_profile_command_message(self, remainder: str) -> None:
        """Parse and execute a profile command topic: <profile_id>/cmd/<enable|disable>."""
        parts = remainder.split("/")
        if len(parts) != 3 or parts[1] != "cmd":
            logger.debug("Profile listener: ignoring unrecognized topic '%s'", remainder)
            return
        profile_id = parts[0].strip()
        action = parts[2].strip().lower()
        if not profile_id:
            logger.debug("Profile listener: empty profile id in '%s'", remainder)
            return
        if action not in ("enable", "disable"):
            logger.debug("Profile listener: unknown action '%s'", action)
            return
        enabled = action == "enable"
        logger.debug(
            "Profile listener: received %s for profile %s",
            action,
            profile_id,
        )
        if not self._profile_set_enabled:
            logger.warning("Profile listener: no handler registered")
            return
        if not self._loop:
            logger.warning(
                "Profile listener: event loop not set; cannot %s profile %s",
                action,
                profile_id,
            )
            return
        try:
            self._loop.call_soon_threadsafe(self._profile_set_enabled, profile_id, enabled)
        except RuntimeError:
            logger.warning(
                "Profile listener: event loop not running; cannot %s profile %s",
                action,
                profile_id,
            )
            return
        logger.info("Profile listener: %s profile %s", action, profile_id)

    def _handle_command_message(self, remainder: str, payload: bytes) -> None:
        """Parse and execute a command topic: <camera_id>/cmd/<action>."""
        from ._stubs import IS_DEMO, demo_server_expired, grace_expired, activation_required
        if activation_required or grace_expired:
            logger.info("Command listener: ignoring command, activation required")
            return
        if IS_DEMO and demo_server_expired:
            logger.info("Command listener: ignoring command, demo trial expired")
            return

        parts = remainder.split("/")
        if len(parts) != 3 or parts[1] != "cmd":
            logger.debug("Command listener: ignoring unrecognized topic structure '%s'", remainder)
            return

        camera_id, _, action = parts
        folder_ids = self._cmd_resolve(camera_id) if self._cmd_resolve else []
        if not folder_ids:
            logger.warning("Command listener: no camera found for '%s'", camera_id)
            return

        if action == "pause":
            try:
                duration = int(payload.decode("utf-8").strip())
            except (ValueError, UnicodeDecodeError):
                logger.warning("Command listener: invalid pause duration payload for camera '%s'", camera_id)
                return
            if duration < 1:
                logger.warning("Command listener: pause duration must be >= 1, got %d", duration)
                return
            names = self._cmd_pause(folder_ids, duration) if self._cmd_pause else []
            logger.info("Command listener: paused %s for %d min", ", ".join(names) or camera_id, duration)
        elif action == "resume":
            names = self._cmd_resume(folder_ids) if self._cmd_resume else []
            logger.info("Command listener: resumed %s", ", ".join(names) or camera_id)
        elif action in ("enable", "disable"):
            enabled = action == "enable"
            if not enabled and self._cmd_resume:
                self._cmd_resume(folder_ids)
            if self._cmd_set_enabled and self._loop:
                self._loop.call_soon_threadsafe(self._cmd_set_enabled, folder_ids, enabled)
                logger.info("Command listener: %s %s", action, camera_id)
        else:
            logger.debug("Command listener: ignoring unknown action '%s'", action)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _disconnect_flags: object,
        reason: object,
        _properties: object = None,
    ) -> None:
        self._connected = False
        if hasattr(reason, "is_failure") and reason.is_failure:
            logger.warning("MQTT disconnected unexpectedly (%s)", reason)
        elif not hasattr(reason, "is_failure") and reason != 0:
            logger.warning("MQTT disconnected unexpectedly (rc=%s)", reason)

    def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
            self._connected = False

    def publish_state_event(self, camera_id: str, state: str, payload: str = "") -> None:
        """Publish a state event: prefix/camera_id/state/{enabled,disabled,paused,resumed}."""
        if not self._client or not self._connected or not self._cmd_listener_enabled or not self._cmd_listener_topic_prefix:
            return
        topic = f"{self._cmd_listener_topic_prefix}/{camera_id}/state/{state}"
        try:
            self._client.publish(
                topic,
                payload.encode("utf-8") if payload else b"",
                qos=self._publish_qos,
                retain=True,
            )
        except Exception:
            logger.error("Failed to publish state event to %s", topic, exc_info=True)

    def _publish_bytes(self, topic: str, payload: bytes) -> None:
        """Publish and log if the client reports an error (helps diagnose VizRec / HA integrations)."""
        if not self._client or not self._connected:
            logger.warning("MQTT publish skipped — not connected (topic=%s)", topic)
            return
        try:
            info = self._client.publish(topic, payload, qos=self._publish_qos)
        except Exception:
            logger.error("MQTT publish exception for topic %s", topic, exc_info=True)
            return
        rc = getattr(info, "rc", None)
        if rc is None and isinstance(info, tuple) and info:
            rc = info[0]
        failed = False
        if rc is not None:
            if hasattr(rc, "is_failure"):
                failed = bool(rc.is_failure)
            else:
                try:
                    failed = int(rc) != getattr(mqtt, "MQTT_ERR_SUCCESS", 0)
                except (TypeError, ValueError):
                    failed = True
        if failed:
            logger.warning("MQTT publish failed rc=%s topic=%s", rc, topic)

    def publish_raw(self, topic: str, payload: str) -> bool:
        """Publish a plain string payload to a topic. Returns True on success."""
        if not self._client or not self._connected or not topic:
            return False
        try:
            self._client.publish(topic, payload.encode("utf-8"), qos=self._publish_qos)
            return True
        except Exception:
            logger.error("publish_raw failed for topic %r", topic, exc_info=True)
            return False

    def publish_notification(
        self,
        notif: MqttNotification,
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        if not self._client or not self._connected or not notif.enabled:
            return

        topic_base = (notif.topic or "").strip().rstrip("/")
        if not topic_base:
            return

        result_dict = result.to_dict()
        correlation_id = str(uuid.uuid4())
        result_dict["correlationId"] = correlation_id
        result_dict = enrich_template_dict(
            result_dict, folder, output_root, "mqtt", source_image_path,
        )
        payload_type = notif.payload
        omit = _parse_bool_setting(getattr(notif, "omitCorrelationIdFromTopic", False), False)
        msg_topic = (
            f"{topic_base}/message"
            if omit
            else f"{topic_base}/message/{correlation_id}"
        )
        img_topic = (
            f"{topic_base}/image"
            if omit
            else f"{topic_base}/image/{correlation_id}"
        )

        if payload_type in ("json", "both"):
            if notif.messageMode == "simple":
                objects = list(dict.fromkeys(
                    d["class"] for d in sorted(
                        result_dict.get("detections", []),
                        key=lambda d: d.get("confidence", 0),
                        reverse=True,
                    )
                ))
                text = json.dumps({
                    "correlationId": correlation_id,
                    "objects": objects,
                    "faces": simple_notification_face_names(result_dict),
                })
                self._publish_bytes(msg_topic, text.encode("utf-8"))
            elif notif.messageMode == "template" and notif.template:
                text = apply_template(notif.template, result_dict)
                self._publish_bytes(msg_topic, text.encode("utf-8"))
            else:
                filtered = filter_fields(result_dict, notif.jsonFields)
                self._publish_bytes(msg_topic, json.dumps(filtered).encode("utf-8"))

        if payload_type in ("image", "both") and result.annotated_image_path:
            try:
                image_data = Path(result.annotated_image_path).read_bytes()
                self._publish_bytes(img_topic, image_data)
            except Exception:
                logger.error("Failed to publish image to MQTT", exc_info=True)

    def publish_all(
        self,
        notifications: list[MqttNotification],
        result: InferenceResult,
        folder: FolderConfig,
        output_root: str,
        source_image_path: str | None = None,
    ) -> None:
        for notif in notifications:
            self.publish_notification(notif, result, folder, output_root, source_image_path)
