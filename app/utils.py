from __future__ import annotations

from collections import Counter
from pathlib import Path

from .models import Annotation, LabelDefinition


def segment_name_from_path(image_path: Path) -> str:
    return image_path.stem


def next_slab_sequence(annotations: list[Annotation], segment_name: str) -> int:
    max_seq = 0
    prefix = f"{segment_name}-"
    for item in annotations:
        if not item.slab_id.startswith(prefix):
            continue
        parts = item.slab_id.split("-")
        if len(parts) < 3:
            continue
        try:
            seq = int(parts[1])
        except ValueError:
            continue
        max_seq = max(max_seq, seq)
    return max_seq + 1


def build_slab_id(segment_name: str, sequence: int, subslab: str = "0000") -> str:
    return f"{segment_name}-{sequence:04d}-{subslab}"


def label_counts(annotations: list[Annotation], labels: list[LabelDefinition]) -> dict[str, int]:
    id_to_name = {label.id: label.name for label in labels}
    counts = Counter([id_to_name.get(item.label_id, item.label_name) for item in annotations])
    return {name: count for name, count in counts.items() if count > 0}


def resolve_icon_path(icons_dir: Path, icon_name: str) -> Path | None:
    candidates = []
    if icon_name:
        candidates.append(icons_dir / icon_name)
    stem = Path(icon_name).stem if icon_name else ""
    if stem:
        candidates.extend(
            [
                icons_dir / f"{stem}.bmp",
                icons_dir / f"{stem}.png",
                icons_dir / f"{stem}.BMP",
                icons_dir / f"{stem}.PNG",
            ]
        )
    for path in candidates:
        if path.exists():
            return path
    return None
