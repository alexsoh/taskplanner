from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote_plus

from .settings_types import FolderConfig


TOKEN_RE = re.compile(r"\{\{([^{}]+)\}\}")


def _value_as_template_string(value: object) -> str:
    """String for ``{{token}}`` substitution: dicts as compact JSON; lists/tuples as comma-separated elements (recursive)."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), default=str)
    if isinstance(value, (list, tuple)):
        return ",".join(_value_as_template_string(v) for v in value)
    return str(value)


def apply_template(template: str, result_dict: dict) -> str:
    text = template
    for key, value in result_dict.items():
        token = "{{" + key + "}}"
        text = text.replace(token, _value_as_template_string(value))
    return text


def _token_value(result_dict: dict, key: str) -> str:
    value = result_dict.get(key.strip(), "")
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return _value_as_template_string(value)
    return str(value)


def simple_notification_face_names(result_dict: dict) -> list[str]:
    """Matched enrollment names for simple JSON payloads (string array, no Unknown).

    Uses rich ``faces`` rows from ``InferenceResult.to_dict()`` after enrich: includes an entry
    only when ``faceMatch`` is present with a non-empty ``name``.
    """
    out: list[str] = []
    for row in result_dict.get("faces") or []:
        if not isinstance(row, dict):
            continue
        fm = row.get("faceMatch")
        if not isinstance(fm, dict):
            continue
        raw = fm.get("name")
        if raw is None:
            continue
        name = str(raw).strip()
        if not name:
            continue
        out.append(name)
    return out


def matched_face_names_for_enrich(result_dict: dict) -> list[str]:
    """Names for ``matchedFaceNames`` template field: prefer ``faces`` order, else person ``detections``."""
    primary = simple_notification_face_names(result_dict)
    if primary:
        return primary
    out: list[str] = []
    for det in result_dict.get("detections") or []:
        if not isinstance(det, dict) or det.get("class") != "person":
            continue
        fm = det.get("faceMatch")
        if not isinstance(fm, dict):
            continue
        raw = fm.get("name")
        if raw is None:
            continue
        name = str(raw).strip()
        if name:
            out.append(name)
    return out


def enrich_template_dict(
    result_dict: dict,
    folder: FolderConfig,
    output_root: str,
    notification_type: str,
    source_image_path: str | None = None,
) -> dict:
    """Merge camera / channel boilerplate and image-path aliases into a copy of ``result_dict``.

    Adds: ``cameraName``, ``filePrefix``, ``notificationType``, ``outputPath``,
    ``detectedImagePath``, ``annotatedImagePath``, ``sourceImagePath``.
    Sets ``friendlyName`` from ``folder.friendlyName`` (normalized strip).
    """
    out = dict(result_dict)
    name = (folder.friendlyName or "").strip()
    out["friendlyName"] = name
    out["cameraName"] = name
    out["filePrefix"] = getattr(folder, "filePrefix", None) or ""
    out["notificationType"] = notification_type
    root = (output_root or "").strip()
    if getattr(folder, "storeOutput", False) and root and name:
        out["outputPath"] = str(Path(root) / name)
    else:
        out["outputPath"] = ""
    ann_raw = out.get("annotatedImageUrl")
    ann = str(ann_raw) if ann_raw else ""
    out["detectedImagePath"] = ann
    out["annotatedImagePath"] = ann
    out["sourceImagePath"] = (source_image_path or "").strip()

    fr = getattr(folder, "faceRecognition", None)
    if fr and getattr(fr, "enabled", False):
        detections = out.get("detections") or []
        known: list[str] = []
        unknown_count = 0
        for det in detections:
            if not isinstance(det, dict) or det.get("class") != "person":
                continue
            fm = det.get("faceMatch")
            if fm and isinstance(fm, dict):
                known.append(fm.get("name", "Unknown"))
            else:
                unknown_count += 1
        all_names = known + ["Unknown"] * unknown_count
        out["detectedPersons"] = ", ".join(all_names) if all_names else ""
        out["knownPersons"] = ", ".join(known) if known else ""
        out["unknownFaceCount"] = unknown_count

    out["matchedFaceNames"] = ", ".join(matched_face_names_for_enrich(out))

    return out


def apply_url_template(template: str, result_dict: dict) -> str:
    """Replace ``{{token}}`` placeholders and URL-encode injected values."""
    return TOKEN_RE.sub(lambda m: quote_plus(_token_value(result_dict, m.group(1))), template)


def filter_fields(data: dict, fields: list[str]) -> dict:
    if not fields:
        return data
    return {k: v for k, v in data.items() if k in fields}
