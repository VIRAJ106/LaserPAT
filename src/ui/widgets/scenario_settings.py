"""
scenario_settings.py — In-app parameter configuration panel.

Exposes every parameter marked "user-defined" in the PS scoring table as a
live control (spinbox / combo / slider).  Changes are written back to the
shared AppConfig object and take effect on the next simulation start.

Covered parameters:
  • World / scene: world size
  • Beacon:        shape, size (px), initial spawn location
  • Camera:        resolution, FOV (deg), monochrome toggle
  • Gimbal:        max pan/tilt rate (deg/s)
  • Simulation:    duration, random seed
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QSizePolicy, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal
from src.config import DistractorConfig


class ScenarioSettingsPanel(QWidget):
    """
    Editable in-app settings panel for all user-configurable scenario parameters.

    Changes are immediately written to the shared ``AppConfig`` instance.
    They take full effect on the next simulation start (workers are recreated).

    Emits ``settings_changed`` whenever any value is modified so that the
    parent Dashboard can show a visual "restart needed" indicator.
    """

    settings_changed = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.cfg = config
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Wrap everything in a scroll area so it works at any window height
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        layout.addWidget(self._build_scene_group())
        layout.addWidget(self._build_beacon_group())
        layout.addWidget(self._build_multi_beacon_group())
        layout.addWidget(self._build_camera_group())
        layout.addWidget(self._build_gimbal_group())
        layout.addWidget(self._build_simulation_group())
        layout.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ── Group builders ─────────────────────────────────────────────────

    def _build_scene_group(self):
        grp = QGroupBox("🌍 Scene / World")
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # World width
        self.spn_world_w = QSpinBox()
        self.spn_world_w.setRange(500, 8000)
        self.spn_world_w.setSingleStep(100)
        self.spn_world_w.setValue(self.cfg.environment.world_size[0])
        self.spn_world_w.valueChanged.connect(self._on_world_size_changed)
        form.addRow("World Width (px):", self.spn_world_w)

        # World height
        self.spn_world_h = QSpinBox()
        self.spn_world_h.setRange(500, 8000)
        self.spn_world_h.setSingleStep(100)
        self.spn_world_h.setValue(self.cfg.environment.world_size[1])
        self.spn_world_h.valueChanged.connect(self._on_world_size_changed)
        form.addRow("World Height (px):", self.spn_world_h)

        grp.setLayout(form)
        return grp

    def _build_multi_beacon_group(self):
        grp = QGroupBox("💡 Multi-Beacon (Optional — earns Innovation points)")
        grp.setToolTip(
            "Add up to 2 distractor light sources.\n"
            "The tracker will discriminate them by bounding-box size.\n"
            "Set 'Track: Target W×H' to the PRIMARY beacon size."
        )
        outer = QVBoxLayout()
        outer.setSpacing(4)
        outer.setContentsMargins(6, 6, 6, 6)

        # Total beacon count (1 = primary only, 2 = 1 distractor, 3 = 2 distractors)
        cnt_form = QFormLayout()
        cnt_form.setSpacing(3)
        self.spn_beacon_count = QSpinBox()
        self.spn_beacon_count.setRange(1, 3)
        self.spn_beacon_count.setValue(1 + len(self.cfg.beacon.distractors))
        self.spn_beacon_count.setToolTip(
            "Total light sources in scene (1 = primary only, 2–3 = add distractors)."
        )
        self.spn_beacon_count.valueChanged.connect(self._on_beacon_count_changed)
        cnt_form.addRow("Total Beacons (1–3):", self.spn_beacon_count)
        outer.addLayout(cnt_form)

        # Size-discriminator target reference
        disc_form = QFormLayout()
        disc_form.setSpacing(3)
        ref_w = self.cfg.beacon.target_size_px[0] if self.cfg.beacon.target_size_px[0] > 0 \
                else self.cfg.beacon.size_px[0]
        ref_h = self.cfg.beacon.target_size_px[1] if self.cfg.beacon.target_size_px[1] > 0 \
                else self.cfg.beacon.size_px[1]
        self.spn_track_w = QSpinBox()
        self.spn_track_w.setRange(1, 80)
        self.spn_track_w.setValue(ref_w)
        self.spn_track_w.setToolTip(
            "Width of the beacon YOU want to track.\n"
            "Set this to the primary beacon width to lock onto it and ignore distractors."
        )
        self.spn_track_w.valueChanged.connect(self._on_target_size_changed)
        disc_form.addRow("Track: Target W (px):", self.spn_track_w)

        self.spn_track_h = QSpinBox()
        self.spn_track_h.setRange(1, 80)
        self.spn_track_h.setValue(ref_h)
        self.spn_track_h.setToolTip(
            "Height of the beacon YOU want to track."
        )
        self.spn_track_h.valueChanged.connect(self._on_target_size_changed)
        disc_form.addRow("Track: Target H (px):", self.spn_track_h)

        # Tolerance label
        self.spn_tolerance = QDoubleSpinBox()
        self.spn_tolerance.setRange(0.1, 0.9)
        self.spn_tolerance.setSingleStep(0.05)
        self.spn_tolerance.setDecimals(2)
        self.spn_tolerance.setValue(self.cfg.beacon.size_tolerance)
        self.spn_tolerance.setToolTip(
            "Acceptance band: 0.5 means blobs within ±50% of target size pass.\n"
            "Lower = stricter (fewer false positives). Higher = looser (fewer misses)."
        )
        self.spn_tolerance.valueChanged.connect(self._on_tolerance_changed)
        disc_form.addRow("Size Tolerance (±%):", self.spn_tolerance)
        outer.addLayout(disc_form)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #444;")
        outer.addWidget(sep)

        # Distractor sub-panels (shown/hidden based on count)
        self.distractor_panels = []
        default_sizes = [(20, 20), (30, 12)]
        for i in range(2):
            d_grp = QGroupBox(f"Distractor {i+1}")
            d_form = QFormLayout()
            d_form.setSpacing(3)
            d_form.setContentsMargins(4, 4, 4, 4)

            # Shape
            d_shape = QComboBox()
            d_shape.addItems(["square", "circle", "cross"])
            if i < len(self.cfg.beacon.distractors):
                d_shape.setCurrentText(self.cfg.beacon.distractors[i].shape)
            d_form.addRow("Shape:", d_shape)

            # Width
            d_w = QSpinBox()
            d_w.setRange(2, 80)
            d_w.setSingleStep(2)
            if i < len(self.cfg.beacon.distractors):
                d_w.setValue(self.cfg.beacon.distractors[i].size_px[0])
            else:
                d_w.setValue(default_sizes[i][0])
            d_form.addRow(f"Width (px):", d_w)

            # Height
            d_h = QSpinBox()
            d_h.setRange(2, 80)
            d_h.setSingleStep(2)
            if i < len(self.cfg.beacon.distractors):
                d_h.setValue(self.cfg.beacon.distractors[i].size_px[1])
            else:
                d_h.setValue(default_sizes[i][1])
            d_form.addRow(f"Height (px):", d_h)

            # Wire changes
            idx = i  # capture for lambda
            d_shape.currentTextChanged.connect(
                lambda v, j=idx: self._update_distractor(j, shape=v))
            d_w.valueChanged.connect(
                lambda v, j=idx: self._update_distractor(j, width=v))
            d_h.valueChanged.connect(
                lambda v, j=idx: self._update_distractor(j, height=v))

            d_grp.setLayout(d_form)
            self.distractor_panels.append((d_grp, d_shape, d_w, d_h))
            outer.addWidget(d_grp)

        grp.setLayout(outer)

        # Show/hide distractor panels based on initial count
        self._update_distractor_visibility(self.spn_beacon_count.value())
        return grp


    def _build_beacon_group(self):
        grp = QGroupBox("🎯 Target (Beacon)")
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # Beacon shape
        self.cmb_beacon_shape = QComboBox()
        self.cmb_beacon_shape.addItems(["square", "circle", "cross"])
        self.cmb_beacon_shape.setCurrentText(self.cfg.beacon.shape)
        self.cmb_beacon_shape.currentTextChanged.connect(self._on_beacon_shape_changed)
        form.addRow("Shape:", self.cmb_beacon_shape)

        # Beacon size — width
        self.spn_beacon_w = QSpinBox()
        self.spn_beacon_w.setRange(2, 80)
        self.spn_beacon_w.setSingleStep(2)
        self.spn_beacon_w.setValue(int(self.cfg.beacon.size_px[0]))
        self.spn_beacon_w.setToolTip("Target width in pixels (2–80 px)")
        self.spn_beacon_w.valueChanged.connect(self._on_beacon_size_changed)
        form.addRow("Size Width (px):", self.spn_beacon_w)

        # Beacon size — height
        self.spn_beacon_h = QSpinBox()
        self.spn_beacon_h.setRange(2, 80)
        self.spn_beacon_h.setSingleStep(2)
        self.spn_beacon_h.setValue(int(self.cfg.beacon.size_px[1]))
        self.spn_beacon_h.setToolTip("Target height in pixels (2–80 px)")
        self.spn_beacon_h.valueChanged.connect(self._on_beacon_size_changed)
        form.addRow("Size Height (px):", self.spn_beacon_h)

        # Initial spawn location
        self.cmb_spawn = QComboBox()
        self.cmb_spawn.addItems(["random", "center", "top-left", "top-right",
                                  "bottom-left", "bottom-right"])
        self.cmb_spawn.setCurrentText(self.cfg.beacon.initial_location
                                      if self.cfg.beacon.initial_location in
                                      ["random", "center"] else "random")
        self.cmb_spawn.setToolTip("Where the target spawns at simulation start")
        self.cmb_spawn.currentTextChanged.connect(self._on_spawn_changed)
        form.addRow("Initial Location:", self.cmb_spawn)

        grp.setLayout(form)
        return grp

    def _build_camera_group(self):
        grp = QGroupBox("📷 Camera")
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # Resolution — width
        self.cmb_res = QComboBox()
        res_options = ["320×240", "640×480", "800×600", "1024×768"]
        self.cmb_res.addItems(res_options)
        cur_res = f"{self.cfg.camera.resolution[0]}×{self.cfg.camera.resolution[1]}"
        if cur_res in res_options:
            self.cmb_res.setCurrentText(cur_res)
        else:
            self.cmb_res.setCurrentText("640×480")
        self.cmb_res.setToolTip("Camera sensor resolution")
        self.cmb_res.currentTextChanged.connect(self._on_resolution_changed)
        form.addRow("Resolution:", self.cmb_res)

        # FOV — horizontal (deg)
        self.spn_fov_h = QDoubleSpinBox()
        self.spn_fov_h.setRange(0.5, 30.0)
        self.spn_fov_h.setSingleStep(0.5)
        self.spn_fov_h.setDecimals(1)
        self.spn_fov_h.setSuffix(" °")
        self.spn_fov_h.setValue(self.cfg.camera.fov_deg[0])
        self.spn_fov_h.setToolTip("Horizontal field-of-view in degrees")
        self.spn_fov_h.valueChanged.connect(self._on_fov_changed)
        form.addRow("FOV Horizontal:", self.spn_fov_h)

        # FOV — vertical (deg)
        self.spn_fov_v = QDoubleSpinBox()
        self.spn_fov_v.setRange(0.5, 30.0)
        self.spn_fov_v.setSingleStep(0.5)
        self.spn_fov_v.setDecimals(1)
        self.spn_fov_v.setSuffix(" °")
        self.spn_fov_v.setValue(self.cfg.camera.fov_deg[1])
        self.spn_fov_v.setToolTip("Vertical field-of-view in degrees")
        self.spn_fov_v.valueChanged.connect(self._on_fov_changed)
        form.addRow("FOV Vertical:", self.spn_fov_v)

        # Monochrome toggle
        self.chk_mono = QCheckBox()
        self.chk_mono.setChecked(self.cfg.camera.monochrome)
        self.chk_mono.stateChanged.connect(self._on_mono_changed)
        form.addRow("Monochrome:", self.chk_mono)

        grp.setLayout(form)
        return grp

    def _build_gimbal_group(self):
        grp = QGroupBox("🕹️ Pan-Tilt (Gimbal)")
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # Max pan rate
        self.spn_pan_rate = QDoubleSpinBox()
        self.spn_pan_rate.setRange(0.5, 30.0)
        self.spn_pan_rate.setSingleStep(0.5)
        self.spn_pan_rate.setDecimals(1)
        self.spn_pan_rate.setSuffix(" °/s")
        self.spn_pan_rate.setValue(self.cfg.camera.gimbal.max_pan_rate_deg_s)
        self.spn_pan_rate.setToolTip("Maximum gimbal pan slew rate (degrees per second)")
        self.spn_pan_rate.valueChanged.connect(self._on_pan_rate_changed)
        form.addRow("Max Pan Rate:", self.spn_pan_rate)

        # Max tilt rate
        self.spn_tilt_rate = QDoubleSpinBox()
        self.spn_tilt_rate.setRange(0.5, 30.0)
        self.spn_tilt_rate.setSingleStep(0.5)
        self.spn_tilt_rate.setDecimals(1)
        self.spn_tilt_rate.setSuffix(" °/s")
        self.spn_tilt_rate.setValue(self.cfg.camera.gimbal.max_tilt_rate_deg_s)
        self.spn_tilt_rate.setToolTip("Maximum gimbal tilt slew rate (degrees per second)")
        self.spn_tilt_rate.valueChanged.connect(self._on_tilt_rate_changed)
        form.addRow("Max Tilt Rate:", self.spn_tilt_rate)

        # Derived info label (read-only)
        pan_px_frame = (self.cfg.camera.gimbal.max_pan_rate_deg_s
                        * (self.cfg.camera.resolution[0] / self.cfg.camera.fov_deg[0])
                        / 30.0)
        self.lbl_derived = QLabel(f"≈ {pan_px_frame:.1f} px/frame @ 30 Hz")
        self.lbl_derived.setStyleSheet("color: #888; font-size: 8pt;")
        form.addRow("Derived speed:", self.lbl_derived)

        grp.setLayout(form)
        return grp

    def _build_simulation_group(self):
        grp = QGroupBox("⏱️ Simulation")
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # Duration
        self.spn_duration = QDoubleSpinBox()
        self.spn_duration.setRange(5.0, 600.0)
        self.spn_duration.setSingleStep(10.0)
        self.spn_duration.setDecimals(0)
        self.spn_duration.setSuffix(" s")
        self.spn_duration.setValue(self.cfg.duration_seconds)
        self.spn_duration.valueChanged.connect(self._on_duration_changed)
        form.addRow("Duration:", self.spn_duration)

        # Random seed
        self.spn_seed = QSpinBox()
        self.spn_seed.setRange(0, 99999)
        self.spn_seed.setValue(self.cfg.seed if self.cfg.seed is not None else 42)
        self.spn_seed.setToolTip("Simulation random seed (reproducibility)")
        self.spn_seed.valueChanged.connect(self._on_seed_changed)
        form.addRow("Random Seed:", self.spn_seed)

        grp.setLayout(form)
        return grp

    # ------------------------------------------------------------------
    # Slots — write changes back to the shared AppConfig
    # ------------------------------------------------------------------

    def _on_world_size_changed(self):
        w = self.spn_world_w.value()
        h = self.spn_world_h.value()
        self.cfg.environment.world_size = (w, h)
        self.settings_changed.emit()

    def _on_beacon_shape_changed(self, text: str):
        self.cfg.beacon.shape = text
        self.settings_changed.emit()

    def _on_beacon_size_changed(self):
        w = self.spn_beacon_w.value()
        h = self.spn_beacon_h.value()
        self.cfg.beacon.size_px = (w, h)
        self.settings_changed.emit()

    def _on_spawn_changed(self, text: str):
        self.cfg.beacon.initial_location = text
        self.settings_changed.emit()

    def _on_resolution_changed(self, text: str):
        try:
            w_str, h_str = text.split("×")
            self.cfg.camera.resolution = (int(w_str), int(h_str))
            self._update_derived_speed()
            self.settings_changed.emit()
        except (ValueError, AttributeError):
            pass

    def _on_fov_changed(self):
        fh = self.spn_fov_h.value()
        fv = self.spn_fov_v.value()
        self.cfg.camera.fov_deg = (fh, fv)
        self._update_derived_speed()
        self.settings_changed.emit()

    def _on_mono_changed(self, state: int):
        self.cfg.camera.monochrome = bool(state)
        self.settings_changed.emit()

    def _on_pan_rate_changed(self, val: float):
        self.cfg.camera.gimbal.max_pan_rate_deg_s = val
        self._update_derived_speed()
        self.settings_changed.emit()

    def _on_tilt_rate_changed(self, val: float):
        self.cfg.camera.gimbal.max_tilt_rate_deg_s = val
        self.settings_changed.emit()

    def _on_duration_changed(self, val: float):
        self.cfg.duration_seconds = val
        self.settings_changed.emit()

    def _on_seed_changed(self, val: int):
        self.cfg.seed = val
        self.settings_changed.emit()

    # ── Multi-beacon slots ─────────────────────────────────────────────

    def _on_beacon_count_changed(self, count: int):
        """Show/hide distractor panels and rebuild cfg.beacon.distractors list."""
        num_distractors = count - 1  # e.g. count=3 → 2 distractors
        self._update_distractor_visibility(count)

        # Rebuild the distractors list from current panel values
        self.cfg.beacon.distractors = []
        for i in range(min(num_distractors, 2)):
            d_grp, d_shape, d_w, d_h = self.distractor_panels[i]
            self.cfg.beacon.distractors.append(DistractorConfig(
                shape=d_shape.currentText(),
                size_px=(d_w.value(), d_h.value()),
                motion="straight",
                initial_location="random",
            ))
        self.cfg.beacon.num_distractors = len(self.cfg.beacon.distractors)
        self.settings_changed.emit()

    def _update_distractor_visibility(self, total_count: int):
        """Show distractor sub-panels only when they are active."""
        for i, (d_grp, d_shape, d_w, d_h) in enumerate(self.distractor_panels):
            d_grp.setVisible(i < total_count - 1)

    def _update_distractor(self, idx: int, shape: str = None,
                           width: int = None, height: int = None):
        """Update a single distractor's config when a control changes."""
        # Ensure list is long enough
        while len(self.cfg.beacon.distractors) <= idx:
            self.cfg.beacon.distractors.append(DistractorConfig())

        d = self.cfg.beacon.distractors[idx]
        if shape is not None:
            d.shape = shape
        if width is not None:
            d.size_px = (width, d.size_px[1])
        if height is not None:
            d.size_px = (d.size_px[0], height)
        self.settings_changed.emit()

    def _on_target_size_changed(self):
        """Update the size-discriminator reference target size."""
        self.cfg.beacon.target_size_px = (
            self.spn_track_w.value(),
            self.spn_track_h.value(),
        )
        self.settings_changed.emit()

    def _on_tolerance_changed(self, val: float):
        self.cfg.beacon.size_tolerance = val
        self.settings_changed.emit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_derived_speed(self):
        """Recompute the px/frame label whenever FOV, resolution, or rate changes."""
        try:
            pan_px_frame = (self.cfg.camera.gimbal.max_pan_rate_deg_s
                            * (self.cfg.camera.resolution[0] / self.cfg.camera.fov_deg[0])
                            / 30.0)
            self.lbl_derived.setText(f"≈ {pan_px_frame:.1f} px/frame @ 30 Hz")
        except (ZeroDivisionError, AttributeError):
            pass

    def refresh_from_config(self):
        """Sync all controls to the current config (e.g. after loading a new YAML)."""
        self.spn_world_w.setValue(self.cfg.environment.world_size[0])
        self.spn_world_h.setValue(self.cfg.environment.world_size[1])
        self.cmb_beacon_shape.setCurrentText(self.cfg.beacon.shape)
        self.spn_beacon_w.setValue(int(self.cfg.beacon.size_px[0]))
        self.spn_beacon_h.setValue(int(self.cfg.beacon.size_px[1]))
        self.cmb_spawn.setCurrentText(
            self.cfg.beacon.initial_location
            if self.cfg.beacon.initial_location in ["random", "center"] else "random"
        )
        cur_res = f"{self.cfg.camera.resolution[0]}×{self.cfg.camera.resolution[1]}"
        if self.cmb_res.findText(cur_res) >= 0:
            self.cmb_res.setCurrentText(cur_res)
        self.spn_fov_h.setValue(self.cfg.camera.fov_deg[0])
        self.spn_fov_v.setValue(self.cfg.camera.fov_deg[1])
        self.chk_mono.setChecked(self.cfg.camera.monochrome)
        self.spn_pan_rate.setValue(self.cfg.camera.gimbal.max_pan_rate_deg_s)
        self.spn_tilt_rate.setValue(self.cfg.camera.gimbal.max_tilt_rate_deg_s)
        self.spn_duration.setValue(self.cfg.duration_seconds)
        self.spn_seed.setValue(self.cfg.seed if self.cfg.seed is not None else 42)
        self.spn_beacon_count.setValue(1 + len(self.cfg.beacon.distractors))
        self._update_distractor_visibility(self.spn_beacon_count.value())
        self._update_derived_speed()
