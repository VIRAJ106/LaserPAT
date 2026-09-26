from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSlider, QLabel, QFormLayout,
    QCheckBox, QGroupBox, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal


class SliderWidget(QWidget):
    value_changed = Signal(float)

    def __init__(self, label: str, min_val: float, max_val: float, step: float, default: float):
        super().__init__()
        self.min_val = min_val
        self.max_val = max_val
        self.step = step

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.lbl = QLabel(f"{label}: {default:.2f}")
        self.lbl.setStyleSheet("color: #e0e0e0; font-size: 9pt;")  # Ensure visibility
        layout.addWidget(self.lbl)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(int((max_val - min_val) / step))
        self.slider.setValue(int((default - min_val) / step))
        self.slider.valueChanged.connect(self.on_change)
        layout.addWidget(self.slider)

        self.setLayout(layout)
        self.label_prefix = label

    def on_change(self, tick: int):
        val = self.min_val + tick * self.step
        self.lbl.setText(f"{self.label_prefix}: {val:.2f}")
        self.value_changed.emit(val)


class ParameterPanel(QWidget):
    def __init__(self, config, proc_worker):
        super().__init__()
        self.cfg = config
        self.proc_worker = proc_worker

        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── PID Sliders ────────────────────────────────────────────────
        pid_box = QGroupBox("PID Controller")
        pid_form = QVBoxLayout()  # Changed from QFormLayout to QVBoxLayout
        pid_form.setSpacing(4)
        pid_form.setContentsMargins(4, 4, 4, 4)

        self.kp_slider = SliderWidget("Kp", 0.0, 3.0, 0.1, self.cfg.control.kp)
        self.kp_slider.value_changed.connect(lambda v: self.update_pid('kp', v))
        pid_form.addWidget(self.kp_slider)

        self.ki_slider = SliderWidget("Ki", 0.0, 1.0, 0.02, self.cfg.control.ki)
        self.ki_slider.value_changed.connect(lambda v: self.update_pid('ki', v))
        pid_form.addWidget(self.ki_slider)

        self.kd_slider = SliderWidget("Kd", 0.0, 2.0, 0.1, self.cfg.control.kd)
        self.kd_slider.value_changed.connect(lambda v: self.update_pid('kd', v))
        pid_form.addWidget(self.kd_slider)

        pid_box.setLayout(pid_form)
        layout.addWidget(pid_box)

        # ── Noise Controls ─────────────────────────────────────────────
        noise_box = QGroupBox("Image Noise (User Selectable)")
        noise_v = QVBoxLayout()
        noise_v.setSpacing(4)
        noise_v.setContentsMargins(4, 4, 4, 4)

        self.noise_slider = SliderWidget(
            "Gaussian Sigma", 0.0, 50.0, 1.0, self.cfg.disturbances.gaussian_sigma
        )
        self.noise_slider.value_changed.connect(self.update_gaussian_sigma)
        noise_v.addWidget(self.noise_slider)

        # Noise type checkboxes
        chk_h = QHBoxLayout()

        self.chk_gaussian = QCheckBox("Gaussian")
        self.chk_gaussian.setChecked(self.cfg.disturbances.gaussian_sigma > 0)
        self.chk_gaussian.stateChanged.connect(self.update_noise_types)
        chk_h.addWidget(self.chk_gaussian)

        self.chk_poisson = QCheckBox("Poisson")
        self.chk_poisson.setChecked(self.cfg.disturbances.poisson)
        self.chk_poisson.stateChanged.connect(self.update_noise_types)
        chk_h.addWidget(self.chk_poisson)

        self.chk_sp = QCheckBox("Salt & Pepper")
        self.chk_sp.setChecked(self.cfg.disturbances.salt_and_pepper_percent > 0)
        self.chk_sp.stateChanged.connect(self.update_noise_types)
        chk_h.addWidget(self.chk_sp)

        noise_v.addLayout(chk_h)

        # Jitter slider
        self.jitter_slider = SliderWidget(
            "Jitter (px)", 0.0, 20.0, 0.5, self.cfg.disturbances.max_displacement_px
        )
        self.jitter_slider.value_changed.connect(self.update_jitter)
        noise_v.addWidget(self.jitter_slider)

        noise_box.setLayout(noise_v)
        layout.addWidget(noise_box)

        self.setLayout(layout)

    # ── Slots ──────────────────────────────────────────────────────────

    def update_pid(self, param, value):
        setattr(self.cfg.control, param, value)
        if self.proc_worker.pid_x:
            if param == 'kp':
                self.proc_worker.pid_x.kp = value
                self.proc_worker.pid_y.kp = value
            elif param == 'ki':
                self.proc_worker.pid_x.ki = value
                self.proc_worker.pid_y.ki = value
            elif param == 'kd':
                self.proc_worker.pid_x.kd = value
                self.proc_worker.pid_y.kd = value

    def update_gaussian_sigma(self, value):
        self.cfg.disturbances.gaussian_sigma = value

    def update_noise_types(self):
        # Disable Gaussian by zeroing sigma
        if not self.chk_gaussian.isChecked():
            self.cfg.disturbances.gaussian_sigma = 0.0
        else:
            # Restore slider value
            tick = self.noise_slider.slider.value()
            self.cfg.disturbances.gaussian_sigma = self.noise_slider.min_val + tick * self.noise_slider.step

        self.cfg.disturbances.poisson = self.chk_poisson.isChecked()

        # Salt & Pepper: 0 when unchecked, 10 % when checked
        self.cfg.disturbances.salt_and_pepper_percent = (
            10.0 if self.chk_sp.isChecked() else 0.0
        )

    def update_jitter(self, value):
        self.cfg.disturbances.max_displacement_px = value
