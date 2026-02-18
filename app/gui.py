from __future__ import annotations

import html
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import zipfile
import posixpath
import xml.etree.ElementTree as ET

try:
    from pyproj import Transformer
except Exception:
    Transformer = None

from PIL import Image, ImageTk
from PIL import ImageFilter

Image.MAX_IMAGE_PIXELS = None

from .annotations_service import load_annotations_xml, save_annotations_xml
from .labels_service import load_labels, save_labels
from .models import Annotation, AnnotationDocument, LabelDefinition
from .utils import build_slab_id, next_slab_sequence, resolve_icon_path, segment_name_from_path


class CounterWindow:
    def __init__(self, master: tk.Misc) -> None:
        self.master = master
        self.window = tk.Toplevel(master)
        self.window.title("Distress and Slab Counter")
        self.window.geometry("980x520")
        self.window.transient(master)
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)
        self.window.withdraw()

        root = ttk.Frame(self.window, padding=8)
        root.pack(fill="both", expand=True)

        summary_frame = ttk.LabelFrame(root, text="Summary")
        summary_frame.pack(fill="x")
        self.summary_table = ttk.Treeview(summary_frame, columns=("metric", "value"), show="headings", height=5)
        self.summary_table.heading("metric", text="Metric")
        self.summary_table.heading("value", text="Value")
        self.summary_table.column("metric", width=260, anchor="w")
        self.summary_table.column("value", width=120, anchor="center")
        self.summary_table.pack(fill="x", expand=True, padx=6, pady=6)

        details_frame = ttk.LabelFrame(root, text="Slabs")
        details_frame.pack(fill="both", expand=True, pady=(8, 0))

        columns = (
            "slab_id",
            "severity",
            "size",
            "tripping_hazard",
            "surface_type",
            "notes",
            "running_slope",
            "cross_slope",
            "latitude",
            "longitude",
            "technician",
            "ramp",
            "utility_present",
        )
        self.details_table = ttk.Treeview(details_frame, columns=columns, show="headings", height=12)
        headings = {
            "slab_id": "SlabID",
            "severity": "Severity",
            "size": "Size",
            "tripping_hazard": "Tripping Hazard",
            "surface_type": "Surface Type",
            "notes": "Notes",
            "running_slope": "Running Slope",
            "cross_slope": "Cross Slope",
            "latitude": "Latitude",
            "longitude": "Longitude",
            "technician": "Technician",
            "ramp": "Ramp",
            "utility_present": "Utility",
        }
        for col in columns:
            self.details_table.heading(col, text=headings[col])
            width = 150 if col in {"slab_id", "notes", "surface_type"} else 110
            self.details_table.column(col, width=width, anchor="w")

        y_scroll = ttk.Scrollbar(details_frame, orient="vertical", command=self.details_table.yview)
        x_scroll = ttk.Scrollbar(details_frame, orient="horizontal", command=self.details_table.xview)
        self.details_table.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.details_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        details_frame.rowconfigure(0, weight=1)
        details_frame.columnconfigure(0, weight=1)

    def show_no_focus(self) -> None:
        if self.window.state() == "withdrawn":
            self.window.deiconify()
            self.window.lift()
            self.master.after(1, self.master.focus_force)

    def toggle_no_focus(self) -> None:
        if self.window.state() == "withdrawn":
            self.window.deiconify()
            self.window.lift()
        else:
            self.window.withdraw()
        self.master.after(1, self.master.focus_force)

    def update_content(
        self,
        image_name: str,
        slab_total: int,
        green_total: int,
        yellow_total: int,
        orange_total: int,
        red_total: int,
        annotations: list[Annotation],
    ) -> None:
        for row in self.summary_table.get_children():
            self.summary_table.delete(row)
        summary_rows = [
            ("Image", image_name),
            ("Total Slabs Evaluated", str(slab_total)),
            ("Green (Good)", str(green_total)),
            ("Yellow (Minor)", str(yellow_total)),
            ("Orange (Moderate)", str(orange_total)),
            ("Red (Severe)", str(red_total)),
        ]
        for row in summary_rows:
            self.summary_table.insert("", "end", values=row)

        for row in self.details_table.get_children():
            self.details_table.delete(row)
        for item in annotations:
            self.details_table.insert(
                "",
                "end",
                values=(
                    item.slab_id,
                    item.label_name,
                    item.size,
                    item.tripping_hazard,
                    item.surface_type,
                    item.notes,
                    item.running_slope,
                    item.cross_slope,
                    item.latitude,
                    item.longitude,
                    item.technician,
                    item.ramp,
                    item.utility_present,
                ),
            )


class LabelsDialog:
    def __init__(
        self,
        master: tk.Misc,
        labels: list[LabelDefinition],
        labels_path: Path,
        on_save: callable,
    ) -> None:
        self.labels = [LabelDefinition.from_dict(item.to_dict()) for item in labels]
        self.labels_path = labels_path
        self.on_save = on_save

        self.window = tk.Toplevel(master)
        self.window.title("Manage Labels")
        self.window.geometry("560x420")

        left = ttk.Frame(self.window)
        right = ttk.Frame(self.window)
        left.pack(side="left", fill="y", padx=8, pady=8)
        right.pack(side="right", fill="both", expand=True, padx=8, pady=8)

        self.listbox = tk.Listbox(left, width=24, height=18)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        form = ttk.Frame(right)
        form.pack(fill="both", expand=True)

        self.var_id = tk.StringVar()
        self.var_key = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_severity = tk.StringVar()
        self.var_icon = tk.StringVar()
        self.var_enabled = tk.BooleanVar(value=True)

        rows = [
            ("ID", self.var_id),
            ("Shortcut key", self.var_key),
            ("Name", self.var_name),
            ("Severity code", self.var_severity),
            ("Icon file", self.var_icon),
        ]
        for idx, (label, var) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=var, width=34).grid(row=idx, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(form, text="Enabled", variable=self.var_enabled).grid(row=5, column=1, sticky="w", pady=4)
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(right)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Add", command=self._add).pack(side="left", padx=4)
        ttk.Button(actions, text="Update", command=self._update).pack(side="left", padx=4)
        ttk.Button(actions, text="Remove", command=self._remove).pack(side="left", padx=4)
        ttk.Button(actions, text="Save", command=self._save).pack(side="right", padx=4)

        self._refresh_list()

    def _selected_index(self) -> int | None:
        if not self.listbox.curselection():
            return None
        return int(self.listbox.curselection()[0])

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for item in sorted(self.labels, key=lambda x: x.id):
            self.listbox.insert("end", f"{item.id} - {item.name}")

    def _on_select(self, _: object) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        item = sorted(self.labels, key=lambda x: x.id)[idx]
        self.var_id.set(str(item.id))
        self.var_key.set(item.key)
        self.var_name.set(item.name)
        self.var_severity.set(item.severity_code)
        self.var_icon.set(item.icon)
        self.var_enabled.set(item.enabled)

    def _read_form(self) -> LabelDefinition | None:
        try:
            label_id = int(self.var_id.get().strip())
        except ValueError:
            messagebox.showerror("Invalid input", "ID must be an integer.")
            return None
        name = self.var_name.get().strip()
        if not name:
            messagebox.showerror("Invalid input", "Name is required.")
            return None
        return LabelDefinition(
            id=label_id,
            key=self.var_key.get().strip(),
            name=name,
            severity_code=self.var_severity.get().strip(),
            icon=self.var_icon.get().strip(),
            enabled=bool(self.var_enabled.get()),
        )

    def _add(self) -> None:
        item = self._read_form()
        if item is None:
            return
        self.labels = [x for x in self.labels if x.id != item.id]
        self.labels.append(item)
        self._refresh_list()

    def _update(self) -> None:
        self._add()

    def _remove(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        item = sorted(self.labels, key=lambda x: x.id)[idx]
        self.labels = [x for x in self.labels if x.id != item.id]
        self._refresh_list()

    def _save(self) -> None:
        save_labels(self.labels_path, sorted(self.labels, key=lambda x: x.id))
        self.on_save()
        self.window.destroy()


class SidewalkAnnotationApp:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.icons_dir = self.project_root / "icons"
        self.labels_path = self.project_root / "labels.json"

        self.root = tk.Tk()
        self.root.title("SWFE Sidewalk Evaluator")
        self.root.geometry("1280x800")

        self.labels: list[LabelDefinition] = []
        self.selected_label_id: int | None = None
        self.label_var = tk.IntVar(value=0)
        self.show_annotations_var = tk.BooleanVar(value=True)

        self.image_paths: list[Path] = []
        self.image_index = -1
        self.current_image_path: Path | None = None
        self.current_image: Image.Image | None = None
        self.current_georef_bounds: dict[str, float] | None = None
        self.current_geo_affine: tuple[float, float, float, float, float, float] | None = None
        self.current_geo_epsg: int | None = None
        self.current_to_wgs84_transformer = None
        self.current_annotations: list[Annotation] = []
        self.icon_cache: dict[int, Image.Image] = {}

        self.zoom = 1.0
        self.view_x = 0.0
        self.view_y = 0.0
        self.min_zoom = 0.0001
        self.max_zoom = 12.0
        self.last_drag_x = 0
        self.last_drag_y = 0
        self._tk_image: ImageTk.PhotoImage | None = None
        self._hq_render_job: str | None = None

        self.status_var = tk.StringVar(value="Load images to start.")
        self.score_var = tk.StringVar(value="Score: 0.00")
        self.counter_window = CounterWindow(self.root)

        self._ensure_default_labels()
        self._load_labels_from_disk()
        self._build_ui()
        self._bind_shortcuts()

    def run(self) -> None:
        self.root.mainloop()

    def _ensure_default_labels(self) -> None:
        if self.labels_path.exists():
            return
        labels = [
            LabelDefinition(id=1, key="1", name="Good", severity_code="1", icon="good.bmp", enabled=True),
            LabelDefinition(id=2, key="2", name="Minor", severity_code="2", icon="minor.bmp", enabled=True),
            LabelDefinition(id=3, key="3", name="Moderate", severity_code="3", icon="moderate.bmp", enabled=True),
            LabelDefinition(id=4, key="4", name="Severe", severity_code="4", icon="severe.bmp", enabled=True),
            LabelDefinition(id=5, key="5", name="Not a Sidewalk", severity_code="0", icon="not_a_sidewalk.bmp", enabled=True),
        ]
        save_labels(self.labels_path, labels)

    def _load_labels_from_disk(self) -> None:
        self.labels = load_labels(self.labels_path)
        enabled_labels = [item for item in self.labels if item.enabled]
        self.selected_label_id = enabled_labels[0].id if enabled_labels else None
        self.label_var.set(self.selected_label_id or 0)
        self.icon_cache.clear()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side="top", fill="x", padx=8, pady=8)

        ttk.Button(toolbar, text="Load image(s)", command=self.load_images).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Load annotations", command=self.load_annotations_manual).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save annotations", command=self.save_annotations).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export JPG", command=self.export_annotated_jpg).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export KMZ", command=self.export_kmz).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Prev", command=self.prev_image).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Next", command=self.next_image).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Manage labels", command=self.open_labels_dialog).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Show/Hide count", command=self.toggle_counter_window).pack(side="left", padx=4)
        ttk.Checkbutton(toolbar, text="Show annotations", variable=self.show_annotations_var, command=self.redraw).pack(side="left", padx=8)

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        labels_panel = ttk.LabelFrame(body, text="Distress labels")
        labels_panel.pack(side="left", fill="y", padx=(8, 4), pady=8)
        self.labels_panel = labels_panel
        self._rebuild_labels_panel()

        viewer_panel = ttk.Frame(body)
        viewer_panel.pack(side="right", fill="both", expand=True, padx=(4, 8), pady=8)

        self.canvas = tk.Canvas(viewer_panel, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.redraw())
        self.canvas.bind("<ButtonPress-2>", self._start_pan)
        self.canvas.bind("<B2-Motion>", self._drag_pan)
        self.canvas.bind("<ButtonPress-1>", self._on_left_click)
        self.canvas.bind("<ButtonPress-3>", self._on_right_click)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(side="bottom", fill="x", padx=8, pady=(0, 8))

    def _rebuild_labels_panel(self) -> None:
        for child in self.labels_panel.winfo_children():
            child.destroy()
        for label in sorted(self.labels, key=lambda x: x.id):
            if not label.enabled:
                continue
            ttk.Radiobutton(
                self.labels_panel,
                text=f"{label.name} ({label.key})",
                value=label.id,
                variable=self.label_var,
                command=self._select_label_from_ui,
            ).pack(anchor="w", padx=8, pady=3)

        ttk.Separator(self.labels_panel, orient="horizontal").pack(fill="x", padx=8, pady=(8, 6))
        ttk.Label(self.labels_panel, text="Real-time Score").pack(anchor="w", padx=8)
        ttk.Label(self.labels_panel, textvariable=self.score_var).pack(anchor="w", padx=8, pady=(2, 6))

    def _bind_shortcuts(self) -> None:
        for label in self.labels:
            if not label.key:
                continue
            self.root.bind(label.key, self._build_shortcut_handler(label.id))

    def _build_shortcut_handler(self, label_id: int):
        def handler(_: tk.Event) -> None:
            self.label_var.set(label_id)
            self._select_label_from_ui()

        return handler

    def _select_label_from_ui(self) -> None:
        self.selected_label_id = int(self.label_var.get()) if self.label_var.get() else None
        selected = self._selected_label()
        if selected is not None:
            self.status_var.set(f"Selected label: {selected.name}")

    def _selected_label(self) -> LabelDefinition | None:
        if self.selected_label_id is None:
            return None
        for label in self.labels:
            if label.id == self.selected_label_id:
                return label
        return None

    def _is_not_sidewalk_label(self, label: LabelDefinition | None) -> bool:
        if label is None:
            return False
        label_name = label.name.strip().lower()
        return label_name == "not a sidewalk" or "not a sidewalk" in label_name

    def _is_not_sidewalk_annotation(self, annotation: Annotation) -> bool:
        label = next((item for item in self.labels if item.id == annotation.label_id), None)
        if self._is_not_sidewalk_label(label):
            return True
        annotation_name = annotation.label_name.strip().lower()
        return annotation_name == "not a sidewalk" or "not a sidewalk" in annotation_name

    def open_labels_dialog(self) -> None:
        LabelsDialog(self.root, self.labels, self.labels_path, self._on_labels_saved)

    def toggle_counter_window(self) -> None:
        self.counter_window.toggle_no_focus()

    def _on_labels_saved(self) -> None:
        self._load_labels_from_disk()
        self._rebuild_labels_panel()
        self._bind_shortcuts()
        self.redraw()

    def load_images(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select image(s)",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.tif *.tiff *.geotiff *.bmp")],
        )
        if not files:
            return
        self.image_paths = [Path(item) for item in files]
        self.image_index = 0
        self._load_current_image()

    def _load_current_image(self) -> None:
        if self.image_index < 0 or self.image_index >= len(self.image_paths):
            return
        image_path = self.image_paths[self.image_index]

        try:
            image = Image.open(image_path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to open image: {exc}")
            return

        self.current_image_path = image_path
        self.current_image = image
        self.current_georef_bounds = None
        self._load_geotiff_georeference(image)
        self.current_annotations = []

        self._reset_view_to_real_size()
        self._autoload_annotations()
        self.counter_window.show_no_focus()
        self._update_counter()
        self.redraw()

        if self.current_geo_affine is not None:
            epsg_text = f"EPSG:{self.current_geo_epsg}" if self.current_geo_epsg is not None else "unknown EPSG"
            self.status_var.set(f"Image loaded: {self.current_image_path.name} (GeoTIFF georeferenced, {epsg_text})")

    def _load_geotiff_georeference(self, image: Image.Image) -> None:
        self.current_geo_affine = None
        self.current_geo_epsg = None
        self.current_to_wgs84_transformer = None

        ifd = getattr(image, "tag_v2", None)
        if ifd is None:
            return

        model_transform = ifd.get(34264)
        if model_transform and len(model_transform) >= 16:
            m = [float(v) for v in model_transform[:16]]
            self.current_geo_affine = (m[0], m[1], m[3], m[4], m[5], m[7])
        else:
            tiepoints = ifd.get(33922)
            scales = ifd.get(33550)
            if tiepoints and scales and len(tiepoints) >= 6 and len(scales) >= 2:
                i = float(tiepoints[0])
                j = float(tiepoints[1])
                x = float(tiepoints[3])
                y = float(tiepoints[4])
                sx = float(scales[0])
                sy = float(scales[1])

                a = sx
                b = 0.0
                c = x - (i * sx)
                d = 0.0
                e = -sy
                f = y + (j * sy)
                self.current_geo_affine = (a, b, c, d, e, f)

        self.current_geo_epsg = self._extract_epsg_from_geotiff(ifd)

        if (
            self.current_geo_epsg is not None
            and self.current_geo_epsg != 4326
            and Transformer is not None
        ):
            try:
                self.current_to_wgs84_transformer = Transformer.from_crs(
                    f"EPSG:{self.current_geo_epsg}",
                    "EPSG:4326",
                    always_xy=True,
                )
            except Exception:
                self.current_to_wgs84_transformer = None

    def _extract_epsg_from_geotiff(self, ifd) -> int | None:
        geokey_dir = ifd.get(34735)
        if not geokey_dir or len(geokey_dir) < 4:
            return None

        values = [int(v) for v in geokey_dir]
        num_keys = values[3]
        base = 4

        projected_epsg: int | None = None
        geographic_epsg: int | None = None

        for idx in range(num_keys):
            offset = base + (idx * 4)
            if offset + 3 >= len(values):
                break
            key_id = values[offset]
            tiff_tag_location = values[offset + 1]
            count = values[offset + 2]
            value_offset = values[offset + 3]

            if tiff_tag_location != 0 or count != 1:
                continue

            if key_id == 3072:
                projected_epsg = value_offset
            elif key_id == 2048:
                geographic_epsg = value_offset

        if projected_epsg and projected_epsg > 0:
            return projected_epsg
        if geographic_epsg and geographic_epsg > 0:
            return geographic_epsg
        return None

    def _load_image_from_kmz(self, kmz_path: Path) -> tuple[Image.Image, dict[str, float]]:
        with zipfile.ZipFile(kmz_path, "r") as archive:
            names = archive.namelist()
            kml_members = [name for name in names if name.lower().endswith(".kml")]
            if not kml_members:
                raise ValueError("KMZ does not contain a KML document.")

            overlay_entries: list[dict[str, object]] = []

            for kml_name in kml_members:
                try:
                    kml_bytes = archive.read(kml_name)
                    root = ET.fromstring(kml_bytes)
                except Exception:
                    continue

                namespace = "{http://www.opengis.net/kml/2.2}"
                overlays = root.findall(f".//{namespace}GroundOverlay")
                if not overlays:
                    overlays = root.findall(".//GroundOverlay")

                for ground_overlay in overlays:
                    href_node = ground_overlay.find(f".//{namespace}Icon/{namespace}href")
                    if href_node is None:
                        href_node = ground_overlay.find(".//Icon/href")
                    href = (href_node.text or "").strip() if href_node is not None else ""
                    if not href or href.startswith("http://") or href.startswith("https://"):
                        continue

                    latlon_box = ground_overlay.find(f".//{namespace}LatLonBox")
                    if latlon_box is None:
                        latlon_box = ground_overlay.find(".//LatLonBox")
                    if latlon_box is None:
                        continue

                    def _read_float(tag: str) -> float | None:
                        node = latlon_box.find(f"{namespace}{tag}")
                        if node is None:
                            node = latlon_box.find(tag)
                        if node is None or node.text is None:
                            return None
                        try:
                            return float(node.text.strip())
                        except ValueError:
                            return None

                    north = _read_float("north")
                    south = _read_float("south")
                    east = _read_float("east")
                    west = _read_float("west")
                    if None in {north, south, east, west}:
                        continue

                    rotation = _read_float("rotation") or 0.0

                    kml_dir = posixpath.dirname(kml_name)
                    image_member = href.lstrip("/")
                    if kml_dir:
                        image_member = posixpath.normpath(posixpath.join(kml_dir, image_member)).lstrip("/")

                    if image_member not in names:
                        href_basename = Path(href).name.lower()
                        fallback = next((n for n in names if Path(n).name.lower() == href_basename), "")
                        if not fallback:
                            continue
                        image_member = fallback

                    try:
                        image_bytes = archive.read(image_member)
                        width, height = Image.open(BytesIO(image_bytes)).size
                    except Exception:
                        continue

                    lat_span = abs(float(north) - float(south))
                    lon_span = abs(float(east) - float(west))
                    area = max(lat_span * lon_span, 1e-18)
                    pixel_density = (width * height) / area

                    overlay_entries.append(
                        {
                            "image_member": image_member,
                            "north": float(north),
                            "south": float(south),
                            "east": float(east),
                            "west": float(west),
                            "rotation": float(rotation),
                            "width": int(width),
                            "height": int(height),
                            "area": area,
                            "pixel_density": pixel_density,
                        }
                    )

            if not overlay_entries:
                raise ValueError("No valid GroundOverlay with local image found in KMZ.")

            union_north = max(entry["north"] for entry in overlay_entries)
            union_south = min(entry["south"] for entry in overlay_entries)
            union_east = max(entry["east"] for entry in overlay_entries)
            union_west = min(entry["west"] for entry in overlay_entries)
            union_area = max((union_north - union_south) * (union_east - union_west), 1e-18)

            for entry in overlay_entries:
                entry["coverage_ratio"] = float(entry["area"]) / union_area

            full_cover_candidates = [entry for entry in overlay_entries if float(entry["coverage_ratio"]) >= 0.85]
            if full_cover_candidates:
                selected = max(full_cover_candidates, key=lambda item: float(item["pixel_density"]))
            else:
                selected = max(overlay_entries, key=lambda item: (float(item["coverage_ratio"]), float(item["pixel_density"])))

            if len(overlay_entries) > 1 and float(selected["coverage_ratio"]) < 0.85:
                messagebox.showwarning(
                    "KMZ quality",
                    "This KMZ seems to be tiled/superoverlay. Current viewer loaded the best single overlay available, "
                    "but maximum quality may still be lower than Google Earth. For full quality, prefer GeoTIFF.",
                )

            if abs(float(selected["rotation"])) > 0.0001:
                messagebox.showwarning(
                    "KMZ rotation",
                    "This KMZ GroundOverlay has rotation. Rotation will be ignored for click coordinates.",
                )

            image_bytes = archive.read(str(selected["image_member"]))
            image = Image.open(BytesIO(image_bytes))

            bounds = {
                "north": float(selected["north"]),
                "south": float(selected["south"]),
                "east": float(selected["east"]),
                "west": float(selected["west"]),
            }
            return image, bounds

    def _pixel_to_latlon(self, pixel_x: float, pixel_y: float) -> tuple[float, float] | None:
        if self.current_geo_affine is None:
            return None

        a, b, c, d, e, f = self.current_geo_affine
        col = float(pixel_x)
        row = float(pixel_y)

        x_geo = (a * col) + (b * row) + c
        y_geo = (d * col) + (e * row) + f

        if self.current_geo_epsg is None or self.current_geo_epsg == 4326:
            return y_geo, x_geo

        if self.current_to_wgs84_transformer is not None:
            try:
                lon, lat = self.current_to_wgs84_transformer.transform(x_geo, y_geo)
                return lat, lon
            except Exception:
                return None

        return None

    def _reset_view_to_real_size(self) -> None:
        if self.current_image is None:
            return
        self.root.update_idletasks()
        self.zoom = 1.0
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        img_w, img_h = self.current_image.size
        self.view_x = max(0.0, (img_w - canvas_w) / 2.0)
        self.view_y = max(0.0, (img_h - canvas_h) / 2.0)

    def _autoload_annotations(self) -> None:
        if self.current_image_path is None:
            return
        xml_path = self.current_image_path.with_suffix(".xml")
        if not xml_path.exists():
            self.status_var.set(f"Image loaded: {self.current_image_path.name} (no annotation file found)")
            return
        try:
            doc = load_annotations_xml(xml_path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load annotations: {exc}")
            return
        self.current_annotations = doc.annotations
        self.status_var.set(f"Image loaded: {self.current_image_path.name} | annotations: {len(self.current_annotations)}")

    def load_annotations_manual(self) -> None:
        if self.current_image is None:
            messagebox.showinfo("Info", "Load an image first.")
            return
        file = filedialog.askopenfilename(title="Select annotations XML", filetypes=[("XML", "*.xml")])
        if not file:
            return
        try:
            doc = load_annotations_xml(Path(file))
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load annotations: {exc}")
            return
        self.current_annotations = doc.annotations
        self._update_counter()
        self.redraw()

    def save_annotations(self) -> None:
        if self.current_image is None or self.current_image_path is None:
            messagebox.showinfo("Info", "Load an image first.")
            return
        doc = AnnotationDocument(
            image_name=self.current_image_path.name,
            image_width=self.current_image.size[0],
            image_height=self.current_image.size[1],
            annotations=self.current_annotations,
        )
        xml_path = self.current_image_path.with_suffix(".xml")
        try:
            save_annotations_xml(xml_path, doc)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to save annotations: {exc}")
            return
        self.status_var.set(f"Saved annotations: {xml_path.name}")

    def export_annotated_jpg(self) -> None:
        if self.current_image is None or self.current_image_path is None:
            messagebox.showinfo("Info", "Load an image first.")
            return
        output = filedialog.asksaveasfilename(
            title="Export JPG",
            defaultextension=".jpg",
            initialfile=f"{self.current_image_path.stem}_annotated.jpg",
            filetypes=[("JPEG", "*.jpg")],
        )
        if not output:
            return

        composed = self.current_image.copy().convert("RGBA")
        for item in self.current_annotations:
            icon = self._icon_for_label(item.label_id)
            if icon is None:
                continue
            px = int(item.x - icon.width / 2)
            py = int(item.y - icon.height / 2)
            composed.alpha_composite(icon, (px, py))
        composed.convert("RGB").save(output, format="JPEG", quality=95)
        self.status_var.set(f"Exported JPEG: {Path(output).name}")

    def export_kmz(self) -> None:
        if self.current_image_path is None:
            messagebox.showinfo("Info", "Load an image first.")
            return

        output = filedialog.asksaveasfilename(
            title="Export KMZ",
            defaultextension=".kmz",
            initialfile=f"{self.current_image_path.stem}_annotations.kmz",
            filetypes=[("KMZ", "*.kmz")],
        )
        if not output:
            return

        georef_annotations: list[Annotation] = []
        for item in self.current_annotations:
            try:
                float(item.latitude)
                float(item.longitude)
            except (TypeError, ValueError):
                continue
            georef_annotations.append(item)

        if not georef_annotations:
            messagebox.showwarning(
                "No coordinates",
                "No annotations with valid Latitude/Longitude were found. KMZ was not created.",
            )
            return

        labels_by_id = {item.id: item for item in self.labels}
        grouped: dict[int, list[Annotation]] = {}
        for item in georef_annotations:
            grouped.setdefault(item.label_id, []).append(item)

        kml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2">',
            "  <Document>",
            f"    <name>{html.escape(self.current_image_path.stem)} Annotations</name>",
            "    <open>1</open>",
            "    <Folder>",
            "      <name>Annotations</name>",
            "      <visibility>1</visibility>",
        ]

        icon_blobs: dict[str, bytes] = {}
        for label_id, annotations in sorted(grouped.items(), key=lambda x: x[0]):
            label = labels_by_id.get(label_id)
            if label is None:
                continue

            style_id = f"label_{label.id}"
            icon_file = f"icons/{style_id}.png"
            icon_img = self._icon_for_label(label.id)
            if icon_img is not None:
                buffer = BytesIO()
                icon_img.convert("RGBA").save(buffer, format="PNG")
                icon_blobs[icon_file] = buffer.getvalue()

            kml_lines.extend(
                [
                    f"    <Style id=\"{style_id}\">",
                    "      <IconStyle>",
                    "        <scale>1.0</scale>",
                    "        <Icon>",
                    f"          <href>{icon_file}</href>",
                    "        </Icon>",
                    "      </IconStyle>",
                    "      <LabelStyle><scale>0.8</scale></LabelStyle>",
                    "    </Style>",
                    "      <Folder>",
                    f"        <name>{html.escape(label.name)}</name>",
                    "        <visibility>1</visibility>",
                ]
            )

            for item in annotations:
                lat = float(item.latitude)
                lon = float(item.longitude)
                name = item.slab_id if item.slab_id.strip() else f"{label.name} Marker"
                description = (
                    f"<![CDATA["
                    f"<b>SlabID:</b> {html.escape(item.slab_id or '-')}<br/>"
                    f"<b>Severity:</b> {html.escape(item.label_name)}<br/>"
                    f"<b>Size:</b> {html.escape(item.size)}<br/>"
                    f"<b>Tripping Hazard:</b> {html.escape(item.tripping_hazard)}<br/>"
                    f"<b>Surface Type:</b> {html.escape(item.surface_type)}<br/>"
                    f"<b>Notes:</b> {html.escape(item.notes)}<br/>"
                    f"<b>Technician:</b> {html.escape(item.technician)}"
                    f"]]>"
                )
                kml_lines.extend(
                    [
                        "        <Placemark>",
                        f"          <name>{html.escape(name)}</name>",
                        f"          <styleUrl>#{style_id}</styleUrl>",
                        f"          <description>{description}</description>",
                        "          <Point>",
                        f"            <coordinates>{lon:.8f},{lat:.8f},0</coordinates>",
                        "          </Point>",
                        "        </Placemark>",
                    ]
                )

            kml_lines.extend(["      </Folder>"])

        kml_lines.extend(["    </Folder>", "  </Document>", "</kml>"])
        kml_payload = "\n".join(kml_lines).encode("utf-8")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("doc.kml", kml_payload)
            for name, content in icon_blobs.items():
                archive.writestr(name, content)

        self.status_var.set(f"Exported KMZ: {Path(output).name}")

    def next_image(self) -> None:
        if not self.image_paths:
            return
        if self.image_index < len(self.image_paths) - 1:
            self.image_index += 1
            self._load_current_image()

    def prev_image(self) -> None:
        if not self.image_paths:
            return
        if self.image_index > 0:
            self.image_index -= 1
            self._load_current_image()

    def _start_pan(self, event: tk.Event) -> None:
        self.last_drag_x = int(event.x)
        self.last_drag_y = int(event.y)

    def _drag_pan(self, event: tk.Event) -> None:
        if self.current_image is None or self.zoom <= 0:
            return
        dx = int(event.x) - self.last_drag_x
        dy = int(event.y) - self.last_drag_y
        self.last_drag_x = int(event.x)
        self.last_drag_y = int(event.y)
        self.view_x -= dx / self.zoom
        self.view_y -= dy / self.zoom
        self.redraw(preview=True)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.current_image is None:
            return
        scale = 1.1 if int(event.delta) > 0 else 0.9
        old_zoom = self.zoom
        self.zoom = max(self.min_zoom, min(self.zoom * scale, self.max_zoom))
        if self.zoom == old_zoom:
            return
        mouse_x = int(event.x)
        mouse_y = int(event.y)
        world_x = self.view_x + mouse_x / old_zoom
        world_y = self.view_y + mouse_y / old_zoom
        self.view_x = world_x - mouse_x / self.zoom
        self.view_y = world_y - mouse_y / self.zoom
        self.redraw(preview=True)

    def _on_left_click(self, event: tk.Event) -> None:
        if self.current_image is None or self.current_image_path is None:
            return
        selected = self._selected_label()
        if selected is None:
            messagebox.showinfo("Info", "Select a label first.")
            return
        image_x = self.view_x + int(event.x) / self.zoom
        image_y = self.view_y + int(event.y) / self.zoom
        image_w, image_h = self.current_image.size
        if image_x < 0 or image_y < 0 or image_x >= image_w or image_y >= image_h:
            return

        slab_id = ""
        if not self._is_not_sidewalk_label(selected):
            segment_name = segment_name_from_path(self.current_image_path)
            seq = next_slab_sequence(self.current_annotations, segment_name)
            slab_id = build_slab_id(segment_name, seq, "0000")
        item = Annotation(
            slab_id=slab_id,
            label_id=selected.id,
            label_name=selected.name,
            x=image_x,
            y=image_y,
        )

        latlon = self._pixel_to_latlon(image_x, image_y)
        if latlon is not None:
            item.latitude = f"{latlon[0]:.8f}"
            item.longitude = f"{latlon[1]:.8f}"

        self.current_annotations.append(item)
        self._update_counter()
        self.redraw()

    def _on_right_click(self, event: tk.Event) -> None:
        if self.current_image is None or not self.current_annotations:
            return
        image_x = self.view_x + int(event.x) / self.zoom
        image_y = self.view_y + int(event.y) / self.zoom

        min_distance_sq = float("inf")
        min_idx = -1
        for idx, item in enumerate(self.current_annotations):
            dx = item.x - image_x
            dy = item.y - image_y
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_distance_sq:
                min_distance_sq = dist_sq
                min_idx = idx

        if min_idx < 0:
            return
        screen_radius_px = 24
        threshold_sq = (screen_radius_px / self.zoom) ** 2
        if min_distance_sq <= threshold_sq:
            self.current_annotations.pop(min_idx)
            self._update_counter()
            self.redraw()

    def _icon_for_label(self, label_id: int) -> Image.Image | None:
        if label_id in self.icon_cache:
            return self.icon_cache[label_id]
        label = next((item for item in self.labels if item.id == label_id), None)
        if label is None:
            return None
        icon_path = resolve_icon_path(self.icons_dir, label.icon)
        if icon_path is None:
            return None
        try:
            icon = Image.open(icon_path).convert("RGBA")
        except Exception:
            return None
        self.icon_cache[label_id] = icon
        return icon

    def _schedule_hq_render(self) -> None:
        if self._hq_render_job is not None:
            self.root.after_cancel(self._hq_render_job)
        self._hq_render_job = self.root.after(90, self._run_hq_render)

    def _run_hq_render(self) -> None:
        self._hq_render_job = None
        if self.current_image is None:
            return
        self.redraw(preview=False)

    def redraw(self, preview: bool = True) -> None:
        self.canvas.delete("all")
        if self.current_image is None:
            self.canvas.create_text(40, 40, anchor="nw", fill="white", text="Load an image to begin.")
            return
        img_w, img_h = self.current_image.size
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        visible_w = canvas_w / self.zoom
        visible_h = canvas_h / self.zoom
        if visible_w >= img_w:
            self.view_x = -((visible_w - img_w) / 2.0)
        else:
            self.view_x = min(max(self.view_x, 0.0), img_w - visible_w)

        if visible_h >= img_h:
            self.view_y = -((visible_h - img_h) / 2.0)
        else:
            self.view_y = min(max(self.view_y, 0.0), img_h - visible_h)

        src_left = max(0.0, self.view_x)
        src_top = max(0.0, self.view_y)
        src_right = min(float(img_w), self.view_x + visible_w)
        src_bottom = min(float(img_h), self.view_y + visible_h)

        viewport = Image.new("RGBA", (canvas_w, canvas_h), (30, 30, 30, 255))

        if src_right > src_left and src_bottom > src_top:
            dst_x = int(round((src_left - self.view_x) * self.zoom))
            dst_y = int(round((src_top - self.view_y) * self.zoom))
            dst_w = max(1, int(round((src_right - src_left) * self.zoom)))
            dst_h = max(1, int(round((src_bottom - src_top) * self.zoom)))

            crop_left = int(src_left)
            crop_top = int(src_top)
            crop_right = min(img_w, max(crop_left + 1, int(src_right + 0.9999)))
            crop_bottom = min(img_h, max(crop_top + 1, int(src_bottom + 0.9999)))

            area_crop = self.current_image.crop((crop_left, crop_top, crop_right, crop_bottom))

            if preview:
                resized_crop = area_crop.resize((dst_w, dst_h), Image.Resampling.BILINEAR).convert("RGBA")
            else:
                resized_crop = area_crop.resize((dst_w, dst_h), Image.Resampling.LANCZOS).convert("RGBA")

            if not preview and self.zoom >= 2.0:
                resized_crop = resized_crop.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=2))

            viewport.alpha_composite(resized_crop, (dst_x, dst_y))

        if self.show_annotations_var.get():
            for item in self.current_annotations:
                x = (item.x - self.view_x) * self.zoom
                y = (item.y - self.view_y) * self.zoom
                if x < -256 or y < -256 or x > canvas_w + 256 or y > canvas_h + 256:
                    continue
                icon = self._icon_for_label(item.label_id)
                if icon is None:
                    continue
                icon_w = max(1, min(512, int(round(icon.width * self.zoom))))
                icon_h = max(1, min(512, int(round(icon.height * self.zoom))))
                icon_scaled = icon.resize((icon_w, icon_h), Image.Resampling.LANCZOS)
                px = int(x - icon_w / 2)
                py = int(y - icon_h / 2)
                viewport.alpha_composite(icon_scaled, (px, py))

        self._tk_image = ImageTk.PhotoImage(viewport)
        self.canvas.create_image(0, 0, image=self._tk_image, anchor="nw")

        if preview:
            self._schedule_hq_render()

        if self.current_image_path is not None:
            self.status_var.set(
                f"{self.current_image_path.name} | {img_w}x{img_h} | annotations: {len(self.current_annotations)} | zoom: {self.zoom:.4f}"
            )

    def _update_counter(self) -> None:
        image_name = self.current_image_path.name if self.current_image_path else "-"
        slab_annotations = [item for item in self.current_annotations if not self._is_not_sidewalk_annotation(item)]
        slab_total = len(slab_annotations)
        id_to_name = {label.id: label.name.lower() for label in self.labels}

        green_total = 0
        yellow_total = 0
        orange_total = 0
        red_total = 0
        for item in slab_annotations:
            name = id_to_name.get(item.label_id, item.label_name.lower())
            if "good" in name:
                green_total += 1
            elif "minor" in name:
                yellow_total += 1
            elif "moderate" in name:
                orange_total += 1
            elif "severe" in name:
                red_total += 1

        if slab_total > 0:
            score = ((green_total + (0.7 * yellow_total) + (0.3 * orange_total)) / slab_total) * 100.0
            score = score * (1.0 - (red_total / slab_total))
            score = max(0.0, min(100.0, score))
        else:
            score = 0.0
        self.score_var.set(f"Score: {score:.2f}")

        self.counter_window.update_content(
            image_name=image_name,
            slab_total=slab_total,
            green_total=green_total,
            yellow_total=yellow_total,
            orange_total=orange_total,
            red_total=red_total,
            annotations=self.current_annotations,
        )
