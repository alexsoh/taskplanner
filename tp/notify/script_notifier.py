from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from .inference_types import InferenceResult
from .notification_retry import NOTIFICATION_MAX_ATTEMPTS, NOTIFICATION_RETRY_DELAY_SEC
from .notification_utils import apply_template, enrich_template_dict
from .settings_types import FolderConfig, ScriptNotification

logger = logging.getLogger("taskplanner.notify..script_notify")

_OUTPUT_LOG_MAX = 32000

# Substrings that imply the annotated/source image path is needed in temp output.
_IMAGE_PATH_TOKEN_MARKERS = (
    "{{detectedImagePath}}",
    "{{annotatedImagePath}}",
    "{{annotatedImageUrl}}",
    "{{sourceImagePath}}",
)


def folder_needs_image_for_scripts(folder: FolderConfig) -> bool:
    for n in folder.scriptNotifications or []:
        if not n.enabled:
            continue
        parts = [(n.scriptPath or "")]
        raw_args = getattr(n, "argumentTemplates", None) or []
        if isinstance(raw_args, str):
            parts.append(raw_args)
        else:
            parts.extend(raw_args)
        blob = "".join(parts)
        if any(m in blob for m in _IMAGE_PATH_TOKEN_MARKERS):
            return True
    return False


def build_script_template_context(
    result: InferenceResult,
    folder: FolderConfig,
    output_root: str,
    source_image_path: str | None,
) -> dict:
    ctx = enrich_template_dict(
        dict(result.to_dict()), folder, output_root, "script", source_image_path,
    )
    ctx["scriptDirectory"] = ""
    return ctx


def _normalize_argument_templates(n: ScriptNotification) -> list[str]:
    raw = getattr(n, "argumentTemplates", None) or []
    if isinstance(raw, str):
        return [raw] if raw else []
    return [str(x) for x in raw]


def _run_subprocess(
    argv: list[str],
    cwd: str,
    timeout: int,
    label: str,
    friendly_name: str,
) -> bool:
    """Run argv with cwd; log output. Return True iff process exits with code 0."""
    logger.info(
        "Script notify [%s] %s: starting %s",
        friendly_name,
        label,
        " ".join(argv[:6]) + (" ..." if len(argv) > 6 else ""),
    )
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "Script notify [%s] %s: timed out after %ds",
            friendly_name,
            label,
            timeout,
        )
        return False
    except OSError as e:
        logger.error(
            "Script notify [%s] %s: failed to start: %s",
            friendly_name,
            label,
            e,
        )
        return False

    combined = ((proc.stdout or "") + (proc.stderr or "")).strip()
    if combined:
        if len(combined) > _OUTPUT_LOG_MAX:
            combined = combined[:_OUTPUT_LOG_MAX] + "\n...[truncated]"
        logger.info(
            "Script notify [%s] %s: exit=%d output:\n%s",
            friendly_name,
            label,
            proc.returncode,
            combined,
        )
    else:
        logger.info(
            "Script notify [%s] %s: exit=%d (no stdout/stderr)",
            friendly_name,
            label,
            proc.returncode,
        )

    if proc.returncode != 0:
        logger.warning(
            "Script notify [%s] %s: non-zero exit code %d",
            friendly_name,
            label,
            proc.returncode,
        )
        return False
    return True


def run_notification(
    notif: ScriptNotification,
    result: InferenceResult,
    folder: FolderConfig,
    output_root: str,
    source_image_path: str | None,
) -> bool:
    """Return True if the script ran and exited 0; False on skip, error, or non-zero exit."""
    if not notif.enabled:
        return False

    friendly_name = folder.friendlyName
    raw_path = (notif.scriptPath or "").strip()
    if not raw_path:
        return False

    base_ctx = build_script_template_context(result, folder, output_root, source_image_path)
    path_templated = apply_template(raw_path, base_ctx).strip()
    if not path_templated:
        logger.error("Script notify [%s] %s: empty path after template", friendly_name, notif.name or notif.id)
        return False

    script_path = Path(path_templated).expanduser()
    try:
        script_resolved = script_path.resolve()
    except OSError:
        logger.error(
            "Script notify [%s] %s: invalid script path %s",
            friendly_name,
            notif.name or notif.id,
            path_templated,
        )
        return False

    if not script_resolved.is_file():
        logger.error(
            "Script notify [%s] %s: script is not a file: %s",
            friendly_name,
            notif.name or notif.id,
            script_resolved,
        )
        return False

    cwd = str(script_resolved.parent)
    try:
        timeout = int(getattr(notif, "timeoutSeconds", 120) or 120)
    except (TypeError, ValueError):
        timeout = 120
    timeout = max(5, min(600, timeout))

    ctx = {**base_ctx, "scriptDirectory": cwd}
    arg_templates = _normalize_argument_templates(notif)
    args = [apply_template(a, ctx) for a in arg_templates]

    label = notif.name.strip() or notif.id
    ext = script_resolved.suffix.lower()

    if ext == ".py":
        argv = [sys.executable, str(script_resolved), *args]
        # Re-running may repeat side effects (webhooks, file writes, etc.); only transport-style failures benefit.
        for attempt in range(1, NOTIFICATION_MAX_ATTEMPTS + 1):
            if attempt > 1:
                time.sleep(NOTIFICATION_RETRY_DELAY_SEC)
            if _run_subprocess(argv, cwd, timeout, label, friendly_name):
                return True
        return False

    if ext in (".ps1",):
        if sys.platform != "win32":
            logger.error(
                "Script notify [%s] %s: PowerShell scripts are not supported on this platform",
                friendly_name,
                label,
            )
            return False
        argv = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_resolved),
            *args,
        ]
        for attempt in range(1, NOTIFICATION_MAX_ATTEMPTS + 1):
            if attempt > 1:
                time.sleep(NOTIFICATION_RETRY_DELAY_SEC)
            if _run_subprocess(argv, cwd, timeout, label, friendly_name):
                return True
        return False

    if ext in (".bat", ".cmd"):
        if sys.platform != "win32":
            logger.error(
                "Script notify [%s] %s: batch scripts are not supported on this platform",
                friendly_name,
                label,
            )
            return False
        argv = ["cmd.exe", "/c", str(script_resolved), *args]
        for attempt in range(1, NOTIFICATION_MAX_ATTEMPTS + 1):
            if attempt > 1:
                time.sleep(NOTIFICATION_RETRY_DELAY_SEC)
            if _run_subprocess(argv, cwd, timeout, label, friendly_name):
                return True
        return False

    logger.error(
        "Script notify [%s] %s: unsupported script extension %r (use .py, .ps1, .bat, or .cmd)",
        friendly_name,
        label,
        ext,
    )
    return False


def run_all(
    notifications: list[ScriptNotification],
    result: InferenceResult,
    folder: FolderConfig,
    output_root: str,
    source_image_path: str | None,
) -> str:
    active = [n for n in notifications if n.enabled]
    if not active:
        return "skipped"
    ok = 0
    fail = 0
    friendly_name = folder.friendlyName
    for n in active:
        try:
            if run_notification(n, result, folder, output_root, source_image_path):
                ok += 1
            else:
                fail += 1
        except Exception:
            logger.exception(
                "Script notify [%s] %s: unexpected error",
                friendly_name,
                n.name or n.id,
            )
            fail += 1
    total = len(active)
    if fail == 0:
        return f"ran ({ok})"
    if ok == 0:
        return f"failed ({fail}/{total})"
    return f"partial ({ok} ok, {fail} failed)"
