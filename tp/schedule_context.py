from __future__ import annotations

from .models import Profile
from .notify.inference_types import Detection, InferenceResult
from .notify.settings_types import FolderConfig


def folder_for_profile(profile: Profile) -> FolderConfig:
    fc = FolderConfig()
    fc.id = profile.id
    fc.friendlyName = profile.name or "profile"
    fc.enabled = True
    fc.watchPath = ""
    fc.storeOutput = False
    return fc


def dummy_inference_result(profile: Profile) -> InferenceResult:
    name = profile.name or "profile"
    return InferenceResult(
        source=f"{name}_taskplanner",
        detections=[
            Detection(cls="person", confidence=0.99, bbox=[10.0, 10.0, 110.0, 110.0]),
        ],
        duration_ms=1.0,
        inference_ms=1.0,
        annotated_image_path=None,
    )
