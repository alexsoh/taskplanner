"""Update checking and installation via Evalex."""

import logging
import platform
import subprocess
from pathlib import Path
from typing import Any

import httpx

from . import __version__, APP_DIR

logger = logging.getLogger(__name__)

APP_SLUG = "taskplanner"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3) for comparison."""
    return tuple(int(x) for x in version_str.lstrip("v").split(".") if x.isdigit())


def check_for_update(
    token: str,
    evalex_base: str = "https://evalex.duckdns.org",
) -> dict[str, Any]:
    """Check for available updates via Evalex.
    
    Args:
        token: Evalex download token
        evalex_base: Base URL of Evalex server
        
    Returns:
        Dictionary with currentVersion, latestVersion, updateAvailable, 
        changeSummary, tokenExpiresAt, or error
    """
    try:
        url = f"{evalex_base}/api/update/check"
        params = {"token": token, "app": APP_SLUG}
        
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params=params)
        
        if response.status_code == 403:
            return {"error": "Invalid, expired, or unauthorized token (403)"}
        
        if response.status_code != 200:
            return {"error": f"Update check failed (HTTP {response.status_code})"}
        
        data = response.json()
        
        # Compare versions
        current = _parse_version(__version__)
        latest = _parse_version(data.get("latest_version", "0.0.0"))
        update_available = latest > current
        
        return {
            "currentVersion": __version__,
            "latestVersion": data.get("latest_version", "0.0.0"),
            "updateAvailable": update_available,
            "changeSummary": data.get("change_summary", ""),
            "tokenExpiresAt": data.get("token_expires_at"),
        }
    except httpx.RequestError as e:
        logger.error(f"Failed to check for updates: {e}")
        return {"error": f"Network error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error checking updates: {e}")
        return {"error": f"Unexpected error: {str(e)}"}


def start_upgrade(
    token: str,
    evalex_base: str = "https://evalex.duckdns.org",
) -> dict[str, Any]:
    """Start an upgrade by running upgrade.sh in a detached subprocess.
    
    Args:
        token: Evalex download token
        evalex_base: Base URL of Evalex server
        
    Returns:
        Dictionary with status and logPath
    """
    try:
        log_dir = APP_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / "upgrade.log"
        
        upgrade_script = APP_DIR / "upgrade.sh"
        if not upgrade_script.exists():
            return {"error": "upgrade.sh not found"}
        
        # Prepare arguments
        args = [
            str(upgrade_script),
            "--token", token,
            "--evalex-base", evalex_base,
        ]
        
        # On Windows, use PowerShell; on Unix, use bash
        if platform.system() == "Windows":
            ps_script = APP_DIR / "upgrade.ps1"
            if not ps_script.exists():
                return {"error": "upgrade.ps1 not found"}

            cmd = [
                "powershell.exe",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_script),
                "-Token",
                token,
                "-EvalexBase",
                evalex_base,
            ]
            # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP (same as PiyoAI)
            creation_flags = 0x08000000 | 0x00000200
            subprocess.Popen(cmd, creationflags=creation_flags, close_fds=False)
        else:
            # Unix: bash
            with open(log_path, "w") as log_file:
                subprocess.Popen(
                    ["bash"] + args,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # Detach from parent
                )
        
        return {
            "status": "upgrade_started",
            "logPath": str(log_path),
        }
    except Exception as e:
        logger.error(f"Failed to start upgrade: {e}")
        return {"error": f"Failed to start upgrade: {str(e)}"}
