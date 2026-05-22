"""Synthetic detection context for notification templates (PiyoAI-compatible shape)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Detection:
    cls: str
    confidence: float
    bbox: list

    face_match: Any = field(default=None, compare=False)
    face_bbox: Optional[list] = field(default=None, compare=False)
    face_det_score: Optional[float] = field(default=None, compare=False)


@dataclass
class InferenceResult:
    source: str
    detections: list = field(default_factory=list)
    duration_ms: float = 0.0
    inference_ms: float = 0.0
    annotated_image_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        def _det_dict(det: Detection) -> dict:
            d = {
                "class": det.cls,
                "confidence": round(det.confidence, 4),
                "bbox": [round(v, 1) for v in det.bbox],
            }
            if det.face_bbox is not None:
                d["faceBbox"] = [round(v, 1) for v in det.face_bbox]
            if det.face_det_score is not None:
                d["faceDetScore"] = round(det.face_det_score, 4)
            if det.face_match is not None and hasattr(det.face_match, "name"):
                d["faceMatch"] = {
                    "personId": getattr(det.face_match, "person_id", ""),
                    "name": det.face_match.name,
                    "similarity": round(getattr(det.face_match, "similarity", 0), 4),
                }
            return d

        faces_out = []
        for det in self.detections:
            if det.cls != "person" or det.face_bbox is None:
                continue
            fe = {
                "bbox": [round(v, 1) for v in det.face_bbox],
                "detScore": round(det.face_det_score or 0.0, 4),
            }
            if det.face_match is not None and hasattr(det.face_match, "name"):
                fe["faceMatch"] = {
                    "personId": getattr(det.face_match, "person_id", ""),
                    "name": det.face_match.name,
                    "similarity": round(getattr(det.face_match, "similarity", 0), 4),
                }
            faces_out.append(fe)

        d = {
            "source": self.source,
            "detections": [_det_dict(det) for det in self.detections],
            "detectionCount": len(self.detections),
            "classNames": list({det.cls for det in self.detections}),
            "faces": faces_out,
            "durationMs": round(self.duration_ms, 1),
            "inferenceMs": round(self.inference_ms, 1),
            "annotatedImageUrl": self.annotated_image_path,
        }
        if self.error:
            d["error"] = self.error
        return d
