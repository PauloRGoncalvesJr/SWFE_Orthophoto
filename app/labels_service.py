from __future__ import annotations

import json
from pathlib import Path

from .models import LabelDefinition


def load_labels(path: Path) -> list[LabelDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    labels_raw = payload.get("labels", [])
    return [LabelDefinition.from_dict(item) for item in labels_raw]


def save_labels(path: Path, labels: list[LabelDefinition]) -> None:
    payload = {
        "labels": [label.to_dict() for label in labels],
        "attribute_table": {
            "SlabID": "SWID-NNNN-AAAA",
            "Severity": "1=Good, 2=Minor defects, 3=Moderate defects, 4=Serious defects",
            "Size": "Narrow(<1m), Regular(1m-1.6m), Wide(>1.6m), Irregular(mixed)",
            "Tripping Hazard": "Yes/No",
            "Surface type": "Concrete, Asphalt, Brick, Mix, Other",
            "Notes": "Free text",
            "Running Slope": "Future feature",
            "Cross Slope": "Future feature",
            "Latitude": "Decimal degrees",
            "Longitude": "Decimal degrees",
            "Technician": "Name",
            "Ramp": "Yes/No",
            "Utility present on panel": "Yes/No",
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
