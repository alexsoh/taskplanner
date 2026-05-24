"""Tests for update functionality."""

from __future__ import annotations

from unittest import mock
from pathlib import Path

import pytest
from tp.db import SessionLocal
from tp.models import AppSettingsRow
from fastapi.testclient import TestClient

from tp.main import app
from tp.settings_store import get_or_create_settings, update_settings, settings_to_api
from tp.updater import check_for_update, start_upgrade, _parse_version


class TestUpdateSettings:
    """Test update settings functionality."""

    def test_update_settings_add_token(self):
        """Test adding an upgrade token."""
        db = SessionLocal()
        try:
            initial = settings_to_api(db)
            assert initial.get("upgradeToken") is None

            data = update_settings(db, None, None, upgrade_token="evlx_test123")
            assert data["upgradeToken"] == "evlx_test123"
        finally:
            db.close()

    def test_update_settings_cannot_clear_existing_token(self):
        """Test that empty string rejects clearing an existing token."""
        db = SessionLocal()
        try:
            # Set initial token
            update_settings(db, None, None, upgrade_token="evlx_test123")

            # Try to clear it with empty string
            with pytest.raises(ValueError, match="Cannot clear upgrade token"):
                update_settings(db, None, None, upgrade_token="")
        finally:
            db.close()

    def test_update_settings_omit_field_preserves_token(self):
        """Test that omitting upgrade token field preserves existing value."""
        db = SessionLocal()
        try:
            # Set initial token
            update_settings(db, None, None, upgrade_token="evlx_test123")

            # Omit upgrade_token (pass None) and update other settings
            data = update_settings(db, {"broker": "mqtt.example.com"}, None)

            # Token should still be there
            assert data["upgradeToken"] == "evlx_test123"
        finally:
            db.close()

    def test_update_settings_evalex_base(self):
        """Test that evalexBase is stored but not exposed in API."""
        db = SessionLocal()
        try:
            row = get_or_create_settings(db)
            assert row.evalex_base == "https://evalex.duckdns.org"
            
            # Verify it's NOT in the API response
            data = settings_to_api(db)
            assert "evalexBase" not in data
        finally:
            db.close()

    def test_update_settings_default_evalex_base(self):
        """Test that default evalexBase is returned by helper."""
        from tp.settings_store import get_evalex_base
        db = SessionLocal()
        try:
            base = get_evalex_base(db)
            assert base == "https://evalex.duckdns.org"
        finally:
            db.close()

    def test_update_settings_preserves_mqtt_telegram(self):
        """Test that updating upgrade token preserves MQTT/Telegram settings."""
        db = SessionLocal()
        try:
            # Set MQTT settings
            update_settings(db, {"broker": "mqtt.local", "port": 1883}, None)

            # Add upgrade token
            data = update_settings(db, None, None, upgrade_token="evlx_token")

            # MQTT settings should still be there
            assert data["mqtt"]["broker"] == "mqtt.local"
            assert data["upgradeToken"] == "evlx_token"
        finally:
            db.close()


class TestParseVersion:
    """Test version parsing."""

    def test_parse_version_normal(self):
        """Test parsing normal semantic version."""
        assert _parse_version("0.1.22") == (0, 1, 22)
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_parse_version_two_parts(self):
        """Test parsing version with only major.minor."""
        assert _parse_version("1.2") == (1, 2, 0)

    def test_parse_version_one_part(self):
        """Test parsing version with only major."""
        assert _parse_version("1") == (1, 0, 0)

    def test_parse_version_invalid(self):
        """Test parsing invalid version returns (0, 0, 0)."""
        assert _parse_version("invalid") == (0, 0, 0)
        assert _parse_version("") == (0, 0, 0)
        assert _parse_version("a.b.c") == (0, 0, 0)

    def test_version_comparison(self):
        """Test version comparison logic."""
        v1 = _parse_version("0.1.22")
        v2 = _parse_version("0.2.0")
        assert v2 > v1

        v3 = _parse_version("0.1.22")
        v4 = _parse_version("0.1.22")
        assert v3 == v4


class TestUpdateCheckEndpoint:
    """Test /api/update/check HTTP handler (eVaultex proxy sends empty body)."""

    @mock.patch("tp.main.get_evalex_base", return_value="https://evalex.example.test")
    @mock.patch("tp.main.get_upgrade_token", return_value="evlx_saved")
    @mock.patch("tp.main.check_for_update")
    def test_check_uses_stored_token_when_body_empty(self, mock_check, _mock_token, _mock_base):
        mock_check.return_value = {
            "currentVersion": "0.1.0",
            "latestVersion": "0.2.0",
            "updateAvailable": True,
            "changeSummary": "",
            "tokenExpiresAt": None,
        }

        client = TestClient(app)
        resp = client.post("/api/update/check", json={})

        assert resp.status_code == 200, resp.text
        mock_check.assert_called_once_with(
            token="evlx_saved",
            evalex_base="https://evalex.example.test",
        )

    @mock.patch("tp.main.get_evalex_base", return_value="https://evalex.example.test")
    @mock.patch("tp.main.get_upgrade_token", return_value="")
    def test_check_missing_token_returns_error_body(self, _mock_token, _mock_base):
        client = TestClient(app)
        resp = client.post("/api/update/check", json={})

        assert resp.status_code == 200, resp.text
        assert "Download Token" in resp.json().get("error", "")


class TestCheckForUpdate:
    """Test update checking."""

    @mock.patch("tp.updater.httpx.Client")
    def test_check_for_update_success(self, mock_client_class):
        """Test successful update check."""
        from tp import __version__
        
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latest_version": "0.2.0",
            "change_summary": "Bug fixes and improvements",
            "token_expires_at": "2026-06-22T00:00:00Z",
        }

        mock_client = mock.Mock()
        mock_client.__enter__ = mock.Mock(return_value=mock_client)
        mock_client.__exit__ = mock.Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = check_for_update("evlx_test")

        assert result["currentVersion"] == __version__
        assert result["latestVersion"] == "0.2.0"
        assert result["updateAvailable"] is True
        assert result["changeSummary"] == "Bug fixes and improvements"

    @mock.patch("tp.updater.httpx.Client")
    def test_check_for_update_no_update_available(self, mock_client_class):
        """Test when no update is available."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "latest_version": "0.1.22",
        }

        mock_client = mock.Mock()
        mock_client.__enter__ = mock.Mock(return_value=mock_client)
        mock_client.__exit__ = mock.Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = check_for_update("evlx_test")

        assert result["updateAvailable"] is False

    @mock.patch("tp.updater.httpx.Client")
    def test_check_for_update_invalid_token(self, mock_client_class):
        """Test invalid token (403)."""
        mock_response = mock.Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Token not valid for taskplanner."}

        mock_client = mock.Mock()
        mock_client.__enter__ = mock.Mock(return_value=mock_client)
        mock_client.__exit__ = mock.Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        with pytest.raises(ValueError, match="taskplanner"):
            check_for_update("invalid_token")

    @mock.patch("tp.updater.httpx.Client")
    def test_check_for_update_network_error(self, mock_client_class):
        """Test network error handling."""
        import httpx

        mock_client_class.side_effect = httpx.ConnectError("Network error")

        with pytest.raises(ValueError, match="Network error"):
            check_for_update("evlx_test")

    @mock.patch("tp.updater.httpx.Client")
    def test_check_for_update_strips_v_prefix(self, mock_client_class):
        """Evalex tags like v0.2.0 compare correctly against running version."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"latest_version": "v9.9.9"}

        mock_client = mock.Mock()
        mock_client.__enter__ = mock.Mock(return_value=mock_client)
        mock_client.__exit__ = mock.Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = check_for_update("evlx_test")

        assert result["latestVersion"] == "9.9.9"
        assert result["updateAvailable"] is True


class TestStartUpgrade:
    """Test upgrade installation."""

    @mock.patch("tp.updater.subprocess.Popen")
    @mock.patch("tp.updater.sys.platform", "linux")
    def test_start_upgrade_unix(self, mock_popen):
        """Test upgrade start on Unix system."""
        with mock.patch.object(Path, "exists", return_value=True):
            log_path = start_upgrade("evlx_test")

        assert log_path.name == "upgrade.log"
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0][0] == "bash"

    @mock.patch("tp.updater.subprocess.Popen")
    @mock.patch("tp.updater.sys.platform", "win32")
    def test_start_upgrade_windows(self, mock_popen):
        """Test upgrade start on Windows."""
        with mock.patch.object(Path, "exists", return_value=True):
            log_path = start_upgrade("evlx_test")

        assert log_path.name == "upgrade.log"
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0][0] == "powershell.exe"

    def test_start_upgrade_missing_bash_script(self):
        """Test upgrade fails if upgrade.sh is missing on Unix."""
        with mock.patch("tp.updater.sys.platform", "linux"):
            with mock.patch.object(Path, "exists", return_value=False):
                with pytest.raises(RuntimeError, match="upgrade.sh"):
                    start_upgrade("evlx_test")

    def test_start_upgrade_missing_ps_script(self):
        """Test upgrade fails if upgrade.ps1 is missing on Windows."""
        with mock.patch("tp.updater.sys.platform", "win32"):
            with mock.patch.object(Path, "exists", return_value=False):
                with pytest.raises(RuntimeError, match="upgrade.ps1"):
                    start_upgrade("evlx_test")
