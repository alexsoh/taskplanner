"""Update checker and in-place upgrader for TaskPlanner.

check_for_update  — queries the evalex server for the latest available version
                    and compares to the running version.
start_upgrade     — spawns the platform-appropriate upgrade script as a
                    fully detached subprocess so it survives the service
                    stopping mid-upgrade.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from . import APP_DIR, __version__

logger = logging.getLogger("taskplanner.updater")

APP_SLUG = "taskplanner"


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) for comparison."""
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def _normalize_latest_tag(raw: str) -> str:
    """Strip a single leading 'v' from evalex version tags (not lstrip)."""
    value = (raw or "").strip()
    if value[:1].lower() == "v":
        return value[1:]
    return value


def check_for_update(token: str = "", evalex_base: str = "") -> dict[str, Any]:
    """Query the evalex server for the latest version and compare to the running version.

    Returns a dict with keys:
        currentVersion  – running version string (e.g. "0.1.46")
        latestVersion   – latest release version (e.g. "0.1.47")
        updateAvailable – bool
        changeSummary   – text from summary.txt (may be empty)
        tokenExpiresAt  – ISO 8601 timestamp string or None

    Raises ValueError with a human-readable message on API errors.
    """
    if not token:
        raise ValueError("Please enter a Download Token and try again.")

    base = (evalex_base or "https://evalex.duckdns.org").rstrip("/")
    url = f"{base}/api/update/check"
    params = {"token": token, "app": APP_SLUG}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params=params)
    except httpx.RequestError as exc:
        raise ValueError(f"Could not reach {base}: {exc}") from exc

    if resp.status_code == 403:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            pass
        raise ValueError(
            detail or "Download token is invalid, expired, or not authorized for this app."
        )
    if not resp.is_success:
        raise ValueError(f"Update API error: HTTP {resp.status_code}")

    data = resp.json()
    latest_tag = _normalize_latest_tag(data.get("latest_version") or "")
    change_summary: str = data.get("change_summary") or ""
    token_expires_at: str | None = data.get("token_expires_at")

    current = _parse_version(__version__)
    latest = _parse_version(latest_tag) if latest_tag else current
    update_available = latest > current

    logger.info(
        "Update check: current=%s latest=%s available=%s",
        __version__,
        latest_tag,
        update_available,
    )

    return {
        "currentVersion": __version__,
        "latestVersion": latest_tag or __version__,
        "updateAvailable": update_available,
        "changeSummary": change_summary,
        "tokenExpiresAt": token_expires_at,
    }


def start_upgrade(
    token: str = "",
    app_dir: Path | None = None,
    evalex_base: str = "",
) -> Path:
    """Spawn the upgrade script as a fully detached process and return immediately.

    On Windows: runs ``upgrade.ps1`` via powershell.exe with CREATE_NO_WINDOW.
    On Linux:   runs ``upgrade.sh`` via bash with a new session.

    Output is redirected to ``logs/upgrade.log`` inside ``app_dir``.

    Returns the Path to the log file.

    Raises:
        RuntimeError  if the upgrade script is not found.
        OSError       if the subprocess cannot be spawned.
    """
    if app_dir is None:
        app_dir = APP_DIR

    log_path = app_dir / "logs" / "upgrade.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        script = app_dir / "upgrade.ps1"
        if not script.exists():
            raise RuntimeError(f"upgrade.ps1 not found at {script}")
        cmd = [
            "powershell.exe",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
        if token:
            cmd += ["-Token", token]
        if evalex_base:
            cmd += ["-EvalexBase", evalex_base]
        creation_flags = 0x08000000 | 0x00000200
        subprocess.Popen(cmd, creationflags=creation_flags, close_fds=False)
        logger.info("Upgrade started (Windows), log: %s", log_path)
    else:
        script = app_dir / "upgrade.sh"
        if not script.exists():
            raise RuntimeError(f"upgrade.sh not found at {script}")
        cmd = ["bash", str(script)]
        if token:
            cmd += ["--token", token]
        if evalex_base:
            cmd += ["--evalex-base", evalex_base]
        with open(log_path, "a", encoding="utf-8") as log_file:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=log_file,
                stderr=log_file,
            )
        logger.info("Upgrade started (Linux), log: %s", log_path)

    return log_path
