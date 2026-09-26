import sys
import os
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QFormLayout, QFileDialog, QTabWidget,
    QStackedWidget, QListWidget, QListWidgetItem, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QSize
from PySide6.QtGui import QImage, QPixmap, QFont

from src.config import load_config
from src.ui.threads import SimWorker, ProcessingWorker, VideoPlaybackWorker
from src.ui.plots import RealTimePlot
from src.ui.widgets.parameter_panel import ParameterPanel
from src.ui.widgets.world_view import WorldViewWidget
from src.ui.widgets.world_view_3d import WorldView3DWidget
from src.ui.widgets.scenario_settings import ScenarioSettingsPanel
from src.ui.analytics_page import AnalyticsPage


class Dashboard(QMainWindow):
    def __init__(self, config_path: str):
        super().__init__()
        self.setWindowTitle("LaserPAT — Mission Control")
        self.resize(1100, 900)  # Reduced height due to compact error plot

        self.cfg = load_config(config_path)
        self._active_source = None  # 'sim' | 'video'

        # Dual-thread workers (simulation mode)
        self.sim_worker = SimWorker(self.cfg)
        self.proc_worker = ProcessingWorker(self.cfg, self.sim_worker)

        # Wire sim → processing
        self.sim_worker.raw_frame_ready.connect(self.proc_worker.on_raw_frame)
        # Wire sim → world view (NEW)
        self.sim_worker.world_state_ready.connect(self.update_world_view)
        # Wire processing → GUI
        self.proc_worker.processed_frame_ready.connect(self.update_frame)
        self.proc_worker.stats_updated.connect(self.update_stats)

        self._init_ui()

    # ------------------------------------------------------------------ #
    #  UI Construction                                                     #
    # ------------------------------------------------------------------ #
    def _init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        
        qss_path = os.path.join(os.path.dirname(__file__), "styles.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        
        main_layout = QHBoxLayout(root)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ══════════════════════════════════════════════════════════════
        # SIDEBAR NAVIGATION
        # ══════════════════════════════════════════════════════════════
        sidebar_container = QWidget()
        sidebar_container.setObjectName("sidebar")
        sidebar_container.setFixedWidth(240)
        sidebar_v = QVBoxLayout(sidebar_container)
        sidebar_v.setContentsMargins(15, 30, 15, 20)
        sidebar_v.setSpacing(20)

        # Logo / Title
        logo_label = QLabel("LASER<b>PAT</b>")
        logo_label.setObjectName("logoLabel")
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar_v.addWidget(logo_label)

        # Navigation List
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        
        for item_text in ["📷 Operations", "🌍 Telemetry", "📈 Analytics", "🎛️ Configuration", "⚖️ A/B Benchmark"]:
            item = QListWidgetItem(item_text)
            item.setSizeHint(QSize(0, 50))
            self.nav_list.addItem(item)
            
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._change_page)
        sidebar_v.addWidget(self.nav_list)
        
        sidebar_v.addStretch()
        
        # State badge moved to sidebar bottom
        self.state_banner = QLabel("IDLE")
        self.state_banner.setObjectName("stateBadge")
        self.state_banner.setAlignment(Qt.AlignCenter)
        self.state_banner.setMinimumHeight(45)
        sidebar_v.addWidget(self.state_banner)

        main_layout.addWidget(sidebar_container)

        # ══════════════════════════════════════════════════════════════
        # STACKED WIDGET (PAGES)
        # ══════════════════════════════════════════════════════════════
        self.stacked_widget = QStackedWidget()
        
        # ──────────────────────────────────────────────────────────────
        # PAGE 1: OPERATIONS (Camera, Stats, Controls)
        # ──────────────────────────────────────────────────────────────
        page_ops = QWidget()
        ops_layout = QVBoxLayout(page_ops)
        ops_layout.setContentsMargins(30, 30, 30, 30)
        ops_layout.setSpacing(20)
        
        ops_title = QLabel("Mission Operations")
        ops_title.setObjectName("pageTitle")
        ops_layout.addWidget(ops_title)

        from src.ui.state_diagram import StateDiagramWidget
        self.fsm_diagram = StateDiagramWidget()
        ops_layout.addWidget(self.fsm_diagram)
        
        # Middle section: Camera and Stats side-by-side
        ops_middle = QHBoxLayout()
        ops_middle.setSpacing(20)
        
        # Camera
        camera_container = QGroupBox("Camera Feed")
        camera_v = QVBoxLayout(camera_container)
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setObjectName("videoFeed")
        self.video_label.setFixedSize(640, 480)
        camera_v.addWidget(self.video_label)
        ops_middle.addWidget(camera_container)
        
        # Right column for Stats and Controls
        ops_right = QVBoxLayout()
        ops_right.setSpacing(20)
        
        stats_grp = QGroupBox("Tracking Statistics")
        stats_form = QFormLayout(stats_grp)
        stats_form.setSpacing(12)
        self.lbl_error = QLabel("—")
        self.lbl_gimbal = QLabel("—")
        self.lbl_target = QLabel("—")
        for lbl in (self.lbl_error, self.lbl_gimbal, self.lbl_target):
            lbl.setProperty("class", "stat")
        stats_form.addRow("Tracking Error:", self.lbl_error)
        stats_form.addRow("Gimbal Pos (px):", self.lbl_gimbal)
        stats_form.addRow("Target Pos (px):", self.lbl_target)
        ops_right.addWidget(stats_grp)
        
        ctrl_grp = QGroupBox("Simulation Controls")
        ctrl_v = QVBoxLayout(ctrl_grp)
        ctrl_v.setSpacing(12)
        self.btn_toggle = QPushButton("▶ Start Simulation")
        self.btn_toggle.setObjectName("btnStart")
        self.btn_toggle.clicked.connect(self.toggle_sim)
        ctrl_v.addWidget(self.btn_toggle)
        
        self.btn_load_video = QPushButton("📂 Load Video (.mp4)")
        self.btn_load_video.setObjectName("btnLoadVideo")
        self.btn_load_video.clicked.connect(self.load_video)
        ctrl_v.addWidget(self.btn_load_video)
        ops_right.addWidget(ctrl_grp)
        # Real-time Error Plot on the right side to save vertical space
        error_container = QGroupBox("Real-Time Error History")
        error_v = QVBoxLayout(error_container)
        error_v.setContentsMargins(5, 5, 5, 5)
        self.error_plot = RealTimePlot("", "Error (px)", max_points=300)
        self.error_plot.setFixedHeight(180) # Compact height
        error_v.addWidget(self.error_plot)
        ops_right.addWidget(error_container)
        
        ops_right.addStretch()
        ops_middle.addLayout(ops_right)
        ops_layout.addLayout(ops_middle)

        self.stacked_widget.addWidget(page_ops)
        
        # ──────────────────────────────────────────────────────────────
        # PAGE 2: TELEMETRY (World Views, Error Plot)
        # ──────────────────────────────────────────────────────────────
        page_telemetry = QWidget()
        tel_layout = QVBoxLayout(page_telemetry)
        tel_layout.setContentsMargins(30, 30, 30, 30)
        tel_layout.setSpacing(20)
        
        tel_title = QLabel("Telemetry & Spatial View")
        tel_title.setObjectName("pageTitle")
        tel_layout.addWidget(tel_title)
        
        world_container = QGroupBox("Spatial Tracking Maps")
        world_v = QVBoxLayout(world_container)
        self.world_tabs = QTabWidget()
        self.world_view = WorldViewWidget(
            world_size=self.cfg.environment.world_size,
            fov_deg=self.cfg.camera.fov_deg
        )
        self.world_tabs.addTab(self.world_view, "2D Top-Down")
        
        self.world_view_3d = WorldView3DWidget(
            world_w=self.cfg.environment.world_size[0],
            world_h=self.cfg.environment.world_size[1]
        )
        self.world_tabs.addTab(self.world_view_3d, "3D Isometric")
        
        # Initial check for tab visibility
        is_moving = self.cfg.environment.platform_motion_type.lower() != "static"
        self.world_tabs.setTabVisible(1, is_moving)
        self._3d_tab_visible = is_moving
        
        world_v.addWidget(self.world_tabs)
        tel_layout.addWidget(world_container, 2)
        self.stacked_widget.addWidget(page_telemetry)
        
        # ──────────────────────────────────────────────────────────────
        # PAGE 3: ANALYTICS (Real-time performance charts)
        # ──────────────────────────────────────────────────────────────
        self.analytics_page = AnalyticsPage(
            turbulence_model=self.cfg.turbulence,
            link_budget_model=getattr(self.cfg, 'link_budget_model', None)
        )
        self.stacked_widget.addWidget(self.analytics_page)
        
        # ──────────────────────────────────────────────────────────────
        # PAGE 4: CONFIGURATION (Tuning, Settings)
        # ──────────────────────────────────────────────────────────────
        page_config = QWidget()
        conf_layout = QVBoxLayout(page_config)
        conf_layout.setContentsMargins(30, 30, 30, 30)
        conf_layout.setSpacing(20)
        
        conf_title = QLabel("Configuration & Tuning")
        conf_title.setObjectName("pageTitle")
        conf_layout.addWidget(conf_title)
        
        conf_scroll_area = QWidget()
        conf_h = QHBoxLayout(conf_scroll_area)
        conf_h.setSpacing(25)
        
        left_conf = QVBoxLayout()
        param_grp = QGroupBox("Live Hardware Tuning")
        param_v = QVBoxLayout(param_grp)
        self.param_panel = ParameterPanel(self.cfg, self.proc_worker)
        param_v.addWidget(self.param_panel)
        left_conf.addWidget(param_grp)
        
        motion_grp = QGroupBox("Environment Simulation")
        motion_v = QVBoxLayout(motion_grp)
        motion_v.setSpacing(15)
        
        weather_h = QHBoxLayout()
        weather_h.addWidget(QLabel("Atmospheric Weather:"))
        self.combo_weather = QComboBox()
        self.combo_weather.addItems(["clear", "haze", "fog", "rain", "low_light"])
        self.combo_weather.setCurrentText(self.cfg.disturbances.weather_preset)
        self.combo_weather.currentTextChanged.connect(self.change_weather)
        weather_h.addWidget(self.combo_weather)
        motion_v.addLayout(weather_h)
        
        t_motion_h = QHBoxLayout()
        t_motion_h.addWidget(QLabel("Target Motion Profile:"))
        self.combo_target_motion = QComboBox()
        self.combo_target_motion.addItems(["Straight", "Circular", "Figure8", "Random"])
        self.combo_target_motion.currentTextChanged.connect(self.change_target_motion)
        t_motion_h.addWidget(self.combo_target_motion)
        motion_v.addLayout(t_motion_h)
        
        p_motion_h = QHBoxLayout()
        p_motion_h.addWidget(QLabel("Platform Disturbance:"))
        self.combo_platform_motion = QComboBox()
        self.combo_platform_motion.addItems(["Static", "Linear", "Circular", "Random"])
        self.combo_platform_motion.setCurrentText(self.cfg.environment.platform_motion_type.capitalize())
        self.combo_platform_motion.currentTextChanged.connect(self.change_platform_motion)
        p_motion_h.addWidget(self.combo_platform_motion)
        motion_v.addLayout(p_motion_h)
        left_conf.addWidget(motion_grp)
        left_conf.addStretch()
        
        right_conf = QVBoxLayout()
        settings_grp = QGroupBox("Core Scenario Settings")
        settings_v = QVBoxLayout(settings_grp)
        self.settings_panel = ScenarioSettingsPanel(self.cfg)
        self.settings_panel.settings_changed.connect(self._on_settings_changed)
        settings_v.addWidget(self.settings_panel)
        
        self.lbl_restart_hint = QLabel("⚠ Restart simulation to apply changes")
        self.lbl_restart_hint.setObjectName("restartHint")
        self.lbl_restart_hint.setAlignment(Qt.AlignCenter)
        self.lbl_restart_hint.setVisible(False)
        settings_v.addWidget(self.lbl_restart_hint)
        right_conf.addWidget(settings_grp)
        right_conf.addStretch()
        
        conf_h.addLayout(left_conf)
        conf_h.addLayout(right_conf)
        conf_layout.addWidget(conf_scroll_area)
        self.stacked_widget.addWidget(page_config)
        
        # PAGE 5: A/B BENCHMARK
        from src.ui.ab_page import ABComparisonPage
        self.ab_page = ABComparisonPage()
        self.stacked_widget.addWidget(self.ab_page)
        
        main_layout.addWidget(self.stacked_widget)

    @Slot(int)
    def _change_page(self, index: int):
        self.stacked_widget.setCurrentIndex(index)

    # ------------------------------------------------------------------ #
    #  Slots                                                               #
    # ------------------------------------------------------------------ #
    @Slot(np.ndarray)
    def update_frame(self, frame_bgr: np.ndarray):
        """Render BGR OpenCV frame onto QLabel via QImage."""
        h, w, ch = frame_bgr.shape
        bytes_per_line = ch * w
        qimg = QImage(frame_bgr.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pix = QPixmap.fromImage(qimg).scaled(
            self.video_label.width(), self.video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.video_label.setPixmap(pix)

    @Slot(dict)
    def update_stats(self, stats: dict):
        state = stats["state"]
        self.fsm_diagram.set_state(state)
        err = stats["error"]

        # State badge color mapping (modern dark theme)
        color_map = {
            "LOCKED":    "#16a085",  # Teal green
            "ACQUIRE":   "#f39c12",  # Orange
            "COAST":     "#3498db",  # Blue
            "SEARCH":    "#e67e22",  # Dark orange
            "REACQUIRE": "#9b59b6",  # Purple
            "LOST":      "#e74c3c",  # Red
        }
        bg = color_map.get(state, "#34495e")  # Dark gray default
        self.state_banner.setText(state)
        self.state_banner.setStyleSheet(f"background: {bg};")

        err_disp = "∞" if err == float('inf') else f"{err:.2f} px"
        self.lbl_error.setText(err_disp)
        self.lbl_gimbal.setText(f"({stats['gimbal_x']:.1f}, {stats['gimbal_y']:.1f})")
        self.lbl_target.setText(f"({stats['target_x']:.1f}, {stats['target_y']:.1f})")

        if err != float('inf'):
            self.error_plot.update_value(min(err, 500))
            
        self.analytics_page.update_stats(stats)

    @Slot(dict)
    def update_world_view(self, world_state: dict):
        """Update the full world view visualization."""
        # Get current tracking state from the processing worker if available
        tracking_state = getattr(self.proc_worker, 'current_state', 'IDLE')
        if hasattr(tracking_state, 'name'):
            tracking_state = tracking_state.name
        
        # Update 2D world view
        self.world_view.update_world(
            beacon_x=world_state["beacon_x"],
            beacon_y=world_state["beacon_y"],
            gimbal_x=world_state["gimbal_x"],
            gimbal_y=world_state["gimbal_y"],
            fov_px=world_state["fov_px"],
            platform_x=world_state.get("platform_x"),
            platform_y=world_state.get("platform_y"),
            platform_is_moving=world_state.get("platform_is_moving", False),
            tracking_state=tracking_state,
            distractors=world_state.get("distractors", []),
            beacon_w=world_state.get("beacon_w", 10),
            beacon_h=world_state.get("beacon_h", 10)
        )
        
        platform_is_moving = world_state.get("platform_is_moving", False)
        
        # Update 3D isometric view only if the platform is actually moving
        if platform_is_moving:
            self.world_view_3d.update_world_3d(
                beacon_x=world_state["beacon_x"],
                beacon_y=world_state["beacon_y"],
                gimbal_x=world_state["gimbal_x"],
                gimbal_y=world_state["gimbal_y"],
                fov_px=world_state["fov_px"],
                platform_x=world_state.get("platform_x"),
                platform_y=world_state.get("platform_y"),
                tracking_state=tracking_state,
                distractors=world_state.get("distractors", []),
                beacon_w=world_state.get("beacon_w", 10),
                beacon_h=world_state.get("beacon_h", 10)
            )
            
        # Dynamically hide/show the 3D tab based on actual motion state
        if hasattr(self, 'world_tabs'):
            # isTabVisible is not available in all PySide6 versions directly like this,
            # but we can use setTabVisible. However, to avoid flickering, let's keep track
            current_visible = getattr(self, '_3d_tab_visible', True)
            if current_visible != platform_is_moving:
                self.world_tabs.setTabVisible(1, platform_is_moving)
                self._3d_tab_visible = platform_is_moving

    # ── Simulation ──────────────────────────────────────────────────────

    @Slot()
    def toggle_sim(self):
        if self._active_source is None:
            # Start simulation
            # Re-create workers so they pick up any settings-panel changes
            self.sim_worker = SimWorker(self.cfg)
            self.proc_worker = ProcessingWorker(self.cfg, self.sim_worker)
            self.sim_worker.raw_frame_ready.connect(self.proc_worker.on_raw_frame)
            self.sim_worker.world_state_ready.connect(self.update_world_view)
            self.proc_worker.processed_frame_ready.connect(self.update_frame)
            self.proc_worker.stats_updated.connect(self.update_stats)

            self.sim_worker.start()
            self.proc_worker.start()
            self._active_source = 'sim'
            self.btn_toggle.setText("⏹  Stop Simulation")
            self.btn_toggle.setObjectName("btnStop")
            self.btn_toggle.setStyle(self.btn_toggle.style())
        else:
            self._stop_all_workers()
            self.world_view.clear_history()
            self.world_view_3d.clear_trail()  # Clear 3D trail too
            self.lbl_restart_hint.setVisible(False)  # Clear hint on stop
            self.btn_toggle.setText("▶  Start Simulation")
            self.btn_toggle.setObjectName("btnStart")
            self.btn_toggle.setStyle(self.btn_toggle.style())
            self.state_banner.setText("IDLE")
            self.state_banner.setStyleSheet("background: #34495e;")
            self.error_plot.reset()
            self.analytics_page.reset()

    # ── Video Playback (Benchmark Performance-2) ────────────────────────

    @Slot()
    def load_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Benchmark Video", "", "Video Files (*.mp4 *.avi *.mkv)"
        )
        if not path:
            return

        # Stop whatever is running
        self._stop_all_workers()
        self.world_view.clear_history("Spatial Map Unavailable in Video Mode")
        self.world_view_3d.clear_trail()

        # Build a fresh video worker
        self.video_worker = VideoPlaybackWorker(path)
        self.proc_worker.sim_worker = self.video_worker

        # Reconnect signals
        self.video_worker.raw_frame_ready.connect(self.proc_worker.on_raw_frame)
        self.proc_worker.processed_frame_ready.connect(self.update_frame)
        self.proc_worker.stats_updated.connect(self.update_stats)

        # Reset proc state machine
        self.proc_worker.kf.__init__()
        self.proc_worker.sm.start_search()

        self.video_worker.start()
        self.proc_worker.start()
        self._active_source = 'video'

        fname = os.path.basename(path)
        self.btn_toggle.setText("⏹  Stop")
        self.btn_toggle.setObjectName("btnStop")
        self.btn_toggle.setStyle(self.btn_toggle.style())
        self.state_banner.setText(f"VIDEO: {fname}")
        self.state_banner.setStyleSheet("background: #2980b9;")  # Blue for video mode

    # ── Motion Selectors ────────────────────────────────────────────────

    @Slot(str)
    def change_weather(self, text: str):
        self.cfg.disturbances.weather_preset = text

    @Slot()
    def _on_settings_changed(self):
        """Show restart hint if simulation is running; any new start will pick up the new config."""
        if self._active_source is not None:
            self.lbl_restart_hint.setVisible(True)

    @Slot(str)
    def change_target_motion(self, motion: str):
        """Change the beacon motion model on-the-fly (simulation only)."""
        if self._active_source == 'sim' and hasattr(self.sim_worker, 'beacon'):
            self.sim_worker.set_beacon_motion(motion)

    @Slot(str)
    def change_platform_motion(self, motion: str):
        """Change the platform motion model on-the-fly (simulation only)."""
        self.cfg.environment.platform_motion_type = motion
        if self._active_source == 'sim' and hasattr(self.sim_worker, 'platform'):
            self.sim_worker.set_platform_motion(motion)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _stop_all_workers(self):
        if self._active_source == 'sim':
            if self.proc_worker.running:
                self.proc_worker.stop()
            if self.sim_worker.running:
                self.sim_worker.stop()
        elif self._active_source == 'video':
            if self.proc_worker.running:
                self.proc_worker.stop()
            if hasattr(self, 'video_worker') and self.video_worker.running:
                self.video_worker.stop()
        self._active_source = None

    def closeEvent(self, event):
        self._stop_all_workers()
        event.accept()


def launch_dashboard(config_path: str):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Dashboard(config_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_dashboard("configs/sih_benchmark.yaml")
