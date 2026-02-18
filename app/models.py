from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LabelDefinition:
    id: int
    key: str
    name: str
    severity_code: str
    icon: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LabelDefinition":
        return cls(
            id=int(payload["id"]),
            key=str(payload.get("key", "")),
            name=str(payload["name"]),
            severity_code=str(payload.get("severity_code", "")),
            icon=str(payload.get("icon", "")),
            enabled=bool(payload.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "severity_code": self.severity_code,
            "icon": self.icon,
            "enabled": self.enabled,
        }


@dataclass(slots=True)
class Annotation:
    slab_id: str
    label_id: int
    label_name: str
    x: float
    y: float
    size: str = "Regular"
    tripping_hazard: str = "No"
    surface_type: str = "Concrete"
    notes: str = ""
    running_slope: str = ""
    cross_slope: str = ""
    latitude: str = ""
    longitude: str = ""
    technician: str = ""
    ramp: str = "No"
    utility_present: str = "No"
    subslab: str = "0000"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Annotation":
        return cls(
            slab_id=str(payload["slab_id"]),
            label_id=int(payload["label_id"]),
            label_name=str(payload.get("label_name", "")),
            x=float(payload["x"]),
            y=float(payload["y"]),
            size=str(payload.get("size", "Regular")),
            tripping_hazard=str(payload.get("tripping_hazard", "No")),
            surface_type=str(payload.get("surface_type", "Concrete")),
            notes=str(payload.get("notes", "")),
            running_slope=str(payload.get("running_slope", "")),
            cross_slope=str(payload.get("cross_slope", "")),
            latitude=str(payload.get("latitude", "")),
            longitude=str(payload.get("longitude", "")),
            technician=str(payload.get("technician", "")),
            ramp=str(payload.get("ramp", "No")),
            utility_present=str(payload.get("utility_present", "No")),
            subslab=str(payload.get("subslab", "0000")),
        )


@dataclass(slots=True)
class AnnotationDocument:
    image_name: str
    image_width: int
    image_height: int
    annotations: list[Annotation] = field(default_factory=list)
