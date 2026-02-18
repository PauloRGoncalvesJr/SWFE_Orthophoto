from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .models import Annotation, AnnotationDocument


def save_annotations_xml(path: Path, doc: AnnotationDocument) -> None:
    root = ET.Element(
        "Annotations",
        {
            "image": doc.image_name,
            "width": str(doc.image_width),
            "height": str(doc.image_height),
        },
    )

    for item in doc.annotations:
        node = ET.SubElement(root, "Annotation")
        ET.SubElement(node, "SlabID").text = item.slab_id
        ET.SubElement(node, "LabelID").text = str(item.label_id)
        ET.SubElement(node, "LabelName").text = item.label_name
        ET.SubElement(node, "X").text = str(item.x)
        ET.SubElement(node, "Y").text = str(item.y)
        ET.SubElement(node, "Severity").text = str(item.label_id)
        ET.SubElement(node, "Size").text = item.size
        ET.SubElement(node, "TrippingHazard").text = item.tripping_hazard
        ET.SubElement(node, "SurfaceType").text = item.surface_type
        ET.SubElement(node, "Notes").text = item.notes
        ET.SubElement(node, "RunningSlope").text = item.running_slope
        ET.SubElement(node, "CrossSlope").text = item.cross_slope
        ET.SubElement(node, "Latitude").text = item.latitude
        ET.SubElement(node, "Longitude").text = item.longitude
        ET.SubElement(node, "Technician").text = item.technician
        ET.SubElement(node, "Ramp").text = item.ramp
        ET.SubElement(node, "UtilityPresent").text = item.utility_present
        ET.SubElement(node, "Subslab").text = item.subslab

    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def load_annotations_xml(path: Path) -> AnnotationDocument:
    tree = ET.parse(path)
    root = tree.getroot()
    image_name = root.attrib.get("image", "")
    width = int(root.attrib.get("width", "0"))
    height = int(root.attrib.get("height", "0"))

    annotations: list[Annotation] = []
    for node in root.findall("Annotation"):
        label_id = int((node.findtext("LabelID") or "0").strip())
        annotation = Annotation(
            slab_id=(node.findtext("SlabID") or "").strip(),
            label_id=label_id,
            label_name=(node.findtext("LabelName") or "").strip(),
            x=float((node.findtext("X") or "0").strip()),
            y=float((node.findtext("Y") or "0").strip()),
            size=(node.findtext("Size") or "Regular").strip(),
            tripping_hazard=(node.findtext("TrippingHazard") or "No").strip(),
            surface_type=(node.findtext("SurfaceType") or "Concrete").strip(),
            notes=(node.findtext("Notes") or "").strip(),
            running_slope=(node.findtext("RunningSlope") or "").strip(),
            cross_slope=(node.findtext("CrossSlope") or "").strip(),
            latitude=(node.findtext("Latitude") or "").strip(),
            longitude=(node.findtext("Longitude") or "").strip(),
            technician=(node.findtext("Technician") or "").strip(),
            ramp=(node.findtext("Ramp") or "No").strip(),
            utility_present=(node.findtext("UtilityPresent") or "No").strip(),
            subslab=(node.findtext("Subslab") or "0000").strip(),
        )
        annotations.append(annotation)

    return AnnotationDocument(
        image_name=image_name,
        image_width=width,
        image_height=height,
        annotations=annotations,
    )
