import os
import yaml
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QTextBrowser, QProgressBar, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal

from src.modes.scenario_runner import run_scenario
from src.evaluation.ab_comparator import compare_runs

class ABWorker(QThread):
    finished_report = Signal(str)
    error_occurred = Signal(str)
    
    def run(self):
        try:
            base_cfg_path = "configs/sih_benchmark.yaml"
            if not os.path.exists(base_cfg_path):
                self.error_occurred.emit("Base config 'configs/sih_benchmark.yaml' not found.")
                return
                
            with open(base_cfg_path, 'r') as f:
                cfg_data = yaml.safe_load(f)
                
            # Set shorter duration for live demo and ensure target starts in view
            cfg_data['scenario']['duration_seconds'] = 30
            if 'beacon' in cfg_data:
                cfg_data['beacon']['initial_location'] = 'center'
            
            os.makedirs("scratch", exist_ok=True)
            
            # Run A: Classical
            path_a = "scratch/ab_classical.yaml"
            cfg_data['detection']['use_cnn_verifier'] = False
            with open(path_a, 'w') as f:
                yaml.dump(cfg_data, f)
                
            # Run B: CNN
            path_b = "scratch/ab_cnn.yaml"
            cfg_data['detection']['use_cnn_verifier'] = True
            with open(path_b, 'w') as f:
                yaml.dump(cfg_data, f)
            
            # Execute headless
            csv_a = run_scenario(path_a, headless=True)
            csv_b = run_scenario(path_b, headless=True)
            
            # Generate markdown report
            report = compare_runs(csv_a, csv_b, "Classical Filter", "AI-Enhanced (CNN)")
            self.finished_report.emit(report)
            
        except Exception as e:
            self.error_occurred.emit(str(e))

class ABComparisonPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        title = QLabel("A/B Live Comparison (Classical vs AI Verifier)")
        title.setObjectName("pageTitle")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #ecf0f1;")
        layout.addWidget(title)
        
        desc = QLabel("Auto-runs two headless 30-second simulations side-by-side using the SIH Benchmark weather conditions, highlighting the lock rate and RMSE improvements when the AI Verifier is enabled.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #bdc3c7; font-size: 14px;")
        layout.addWidget(desc)
        
        self.btn_run = QPushButton("▶ Run Live 30s Comparison")
        self.btn_run.setFixedHeight(50)
        self.btn_run.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:disabled { background-color: #7f8c8d; }
        """)
        self.btn_run.clicked.connect(self.start_comparison)
        layout.addWidget(self.btn_run)
        
        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        
        # Results area
        grp = QGroupBox("Comparison Results")
        grp_layout = QVBoxLayout(grp)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setStyleSheet("background-color: #1e272e; color: #ecf0f1; font-family: Consolas, monospace; font-size: 14px;")
        grp_layout.addWidget(self.text_browser)
        
        layout.addWidget(grp)
        
        self.worker = None

    def start_comparison(self):
        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running Simulations (Please Wait)...")
        self.progress.setVisible(True)
        self.text_browser.clear()
        
        self.worker = ABWorker()
        self.worker.finished_report.connect(self.on_success)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.start()
        
    def on_success(self, markdown_report: str):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶ Run Live 30s Comparison")
        self.progress.setVisible(False)
        self.text_browser.setMarkdown(markdown_report)
        
    def on_error(self, err: str):
        self.btn_run.setEnabled(True)
        self.btn_run.setText("▶ Run Live 30s Comparison")
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Comparison Error", str(err))
