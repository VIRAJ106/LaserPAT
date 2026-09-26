import math
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout
)
import numpy as np

class AnalyticsPage(QWidget):
    def __init__(self, turbulence_model=None, link_budget_model=None, parent=None):
        super().__init__(parent)
        self._turb = turbulence_model
        self._lb = link_budget_model

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header
        title = QLabel("Performance Analytics")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        # ── Atmospheric Physics Panel ─────────────────────────────────────
        atm_grp = QGroupBox("⚡ Atmospheric Physics  (Cn²-derived  ·  Andrews & Phillips 2005)")
        atm_form = QFormLayout(atm_grp)
        atm_form.setSpacing(10)
        atm_form.setContentsMargins(20, 15, 20, 15)

        def _metric_label(value_str: str, color: str = "#38bdf8") -> QLabel:
            lbl = QLabel(value_str)
            lbl.setStyleSheet(
                f"color: {color}; font-weight: bold; font-size: 13px;"
                "background: transparent; padding: 2px 6px;"
            )
            return lbl

        self.lbl_r0      = _metric_label("—", "#10b981")   # Fried r₀
        self.lbl_rytov   = _metric_label("—", "#38bdf8")   # Rytov variance
        self.lbl_si      = _metric_label("—", "#f59e0b")   # Scintillation index
        self.lbl_theta   = _metric_label("—", "#a855f7")   # Isoplanatic angle
        self.lbl_sigma   = _metric_label("—", "#ec4899")   # Derived image σ
        self.lbl_regime  = _metric_label("—", "#e74c3c")   # Turbulence regime

        atm_form.addRow("Fried Parameter r₀:", self.lbl_r0)
        atm_form.addRow("Rytov Variance σ²ᴿ:", self.lbl_rytov)
        atm_form.addRow("Scintillation Index:", self.lbl_si)
        atm_form.addRow("Isoplanatic Angle θ₀:", self.lbl_theta)
        atm_form.addRow("Derived Image Noise σ:", self.lbl_sigma)
        atm_form.addRow("Turbulence Regime:", self.lbl_regime)

        layout.addWidget(atm_grp)

        # ── Link Budget Panel ─────────────────────────────────────────────
        lb_grp = QGroupBox("📡 Real-Time Link Budget (Friis & Pointing Loss)")
        lb_form = QFormLayout(lb_grp)
        lb_form.setSpacing(10)
        lb_form.setContentsMargins(20, 15, 20, 15)

        self.lbl_lb_err    = _metric_label("—", "#38bdf8")
        self.lbl_lb_geom   = _metric_label("—", "#f59e0b")
        self.lbl_lb_point  = _metric_label("—", "#ec4899")
        self.lbl_lb_rx_pwr = _metric_label("—", "#10b981")
        self.lbl_lb_margin = _metric_label("—", "#a855f7")

        lb_form.addRow("Angular Pointing Error:", self.lbl_lb_err)
        lb_form.addRow("Geometric Path Loss:", self.lbl_lb_geom)
        lb_form.addRow("Pointing Loss (Gaussian):", self.lbl_lb_point)
        lb_form.addRow("Total Received Power:", self.lbl_lb_rx_pwr)
        lb_form.addRow("Link Margin:", self.lbl_lb_margin)

        layout.addWidget(lb_grp)

        # Populate once with initial turbulence model (if provided)
        if self._turb is not None:
            self._refresh_turbulence_panel()

        # ── Charts Grid (2×2) ────────────────────────────────────────────
        grid = QVBoxLayout()
        grid.setSpacing(20)
        row1 = QHBoxLayout()
        row1.setSpacing(20)
        row2 = QHBoxLayout()
        row2.setSpacing(20)

        # Style globals for pyqtgraph to match dark theme
        pg.setConfigOption('background', '#0f172a')
        pg.setConfigOption('foreground', '#94a3b8')

        # Custom ViewBox styles to match glassmorphism borders
        plot_opts = {'border': '#143a52'}

        # 1. Angular Error vs Time
        self.plot_error = pg.PlotWidget(title="TRACKING ERROR (px) VS TIME", **plot_opts)
        self.plot_error.showGrid(x=True, y=True, alpha=0.2)
        self.curve_error = self.plot_error.plot(pen=pg.mkPen('#38bdf8', width=2))
        row1.addWidget(self.plot_error)

        # 2. FPS + Processing Latency
        self.plot_fps = pg.PlotWidget(title="FPS & PROCESSING LATENCY", **plot_opts)
        self.plot_fps.showGrid(x=True, y=True, alpha=0.2)
        self.plot_fps.addLegend(offset=(10, 10))
        self.curve_fps = self.plot_fps.plot(name="FPS", pen=pg.mkPen('#10b981', width=2))
        self.curve_lat = self.plot_fps.plot(name="Latency (ms)", pen=pg.mkPen('#ec4899', width=2))
        row1.addWidget(self.plot_fps)

        # 3. Detection Confidence (%)
        self.plot_conf = pg.PlotWidget(title="DETECTION CONFIDENCE (%)", **plot_opts)
        self.plot_conf.setYRange(0, 105)
        self.plot_conf.showGrid(x=True, y=True, alpha=0.2)
        self.curve_conf = self.plot_conf.plot(pen=pg.mkPen('#a855f7', width=2))
        row2.addWidget(self.plot_conf)

        # 4. Error Distribution (BarGraph)
        self.plot_dist = pg.PlotWidget(title="ERROR DISTRIBUTION (LAST 200 FRAMES)", **plot_opts)
        self.plot_dist.showGrid(x=True, y=True, alpha=0.2)
        self.bar_dist = pg.BarGraphItem(x=[], height=[], width=0.8, brush='#38bdf8')
        self.plot_dist.addItem(self.bar_dist)
        row2.addWidget(self.plot_dist)

        grid.addLayout(row1)
        grid.addLayout(row2)
        layout.addLayout(grid)

        # Data buffers
        self.max_pts = 200
        self.data_err  = np.zeros(self.max_pts)
        self.data_fps  = np.zeros(self.max_pts)
        self.data_lat  = np.zeros(self.max_pts)
        self.data_conf = np.zeros(self.max_pts)

    def set_turbulence_model(self, model) -> None:
        """Inject (or update) the TurbulenceModel and refresh the panel."""
        self._turb = model
        self._refresh_turbulence_panel()

    def _refresh_turbulence_panel(self) -> None:
        """Recompute all turbulence metrics and push them to the UI labels."""
        if self._turb is None:
            return
        metrics = self._turb.compute_all(distance_km=1.0)

        r0    = metrics["r0_cm"]
        rv    = metrics["rytov_variance"]
        si    = metrics["scintillation_index"]
        theta = metrics["isoplanatic_angle_urad"]
        sig   = metrics["image_sigma_px"]
        reg   = metrics["regime"]

        self.lbl_r0.setText(f"{r0:.2f} cm")
        self.lbl_rytov.setText(f"{rv:.2e}")
        self.lbl_si.setText(f"{si:.4f}")
        self.lbl_theta.setText(f"{theta:.2f} μrad")
        self.lbl_sigma.setText(f"{sig:.2f} px  (used for Gaussian noise)")

        regime_colors = {
            "Weak":      "#10b981",
            "Moderate":  "#f59e0b",
            "Strong":    "#f97316",
            "Saturated": "#e74c3c",
        }
        color = regime_colors.get(reg, "#94a3b8")
        self.lbl_regime.setText(reg)
        self.lbl_regime.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 13px;"
            "background: transparent; padding: 2px 6px;"
        )


    def set_link_budget_model(self, model):
        self._lb = model

    def update_stats(self, stats):
        err = stats.get("error", float('inf'))
        fps = stats.get("fps", 0)
        
        # Update Link Budget if available and error is valid
        if self._lb is not None and err != float('inf'):
            lb_res = self._lb.compute(distance_km=1.0, pointing_error_px=err)
            self.lbl_lb_err.setText(f"{lb_res['pointing_error_urad']:.2f} μrad")
            self.lbl_lb_geom.setText(f"{lb_res['geometric_loss_dB']:.2f} dB")
            self.lbl_lb_point.setText(f"{lb_res['pointing_loss_dB']:.2f} dB")
            self.lbl_lb_rx_pwr.setText(f"{lb_res['received_power_dBm']:.2f} dBm")
            margin = lb_res['margin_dB']
            status = lb_res['link_status']
            color = "#10b981" if status == "UP" else "#e74c3c"
            self.lbl_lb_margin.setText(f"{margin:.2f} dB ({status})")
            self.lbl_lb_margin.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px; background: transparent; padding: 2px 6px;")
        lat = stats.get("latency_ms", 0)
        conf = stats.get("confidence", 0)
        
        if err == float('inf'):
            err = 0  # Ignore inf for plotting to avoid scaling issues
            
        # Shift data
        self.data_err[:-1] = self.data_err[1:]
        self.data_err[-1] = err
        
        self.data_fps[:-1] = self.data_fps[1:]
        self.data_fps[-1] = fps
        
        self.data_lat[:-1] = self.data_lat[1:]
        self.data_lat[-1] = lat
        
        self.data_conf[:-1] = self.data_conf[1:]
        self.data_conf[-1] = conf
        
        self.curve_error.setData(self.data_err)
        self.curve_fps.setData(self.data_fps)
        self.curve_lat.setData(self.data_lat)
        self.curve_conf.setData(self.data_conf)
        
        # Histogram for error
        # Ignore 0s if they mean inf (unless true error is 0)
        valid_errs = self.data_err[self.data_err > 0]
        if len(valid_errs) > 0:
            hist, bins = np.histogram(valid_errs, bins=20, range=(0, max(20, np.max(valid_errs)+1)))
            self.bar_dist.setOpts(x=bins[:-1], height=hist, width=(bins[1]-bins[0])*0.8)
        else:
            self.bar_dist.setOpts(x=[], height=[])
        
    def reset(self):
        self.data_err.fill(0)
        self.data_fps.fill(0)
        self.data_lat.fill(0)
        self.data_conf.fill(0)
        self.curve_error.setData(self.data_err)
        self.curve_fps.setData(self.data_fps)
        self.curve_lat.setData(self.data_lat)
        self.curve_conf.setData(self.data_conf)
        self.bar_dist.setOpts(x=[], height=[])
