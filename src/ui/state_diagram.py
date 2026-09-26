from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

class StateDiagramWidget(QWidget):
    """
    Animated State Transition Visualization.
    Highlights the current state node to make the 7-state SM visually obvious.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(5)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.states = ["IDLE", "SEARCH", "ACQUIRE", "LOCKED", "COAST", "LOST", "REACQUIRE"]
        self.labels = {}
        
        for st in self.states:
            lbl = QLabel(st)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(self._get_style(False, st))
            self.labels[st] = lbl
            self.layout.addWidget(lbl)
            
            if st != self.states[-1]:
                arrow = QLabel("→")
                arrow.setStyleSheet("color: #64748b; font-weight: bold;")
                self.layout.addWidget(arrow)
                
    def _get_style(self, active: bool, state_name: str) -> str:
        color_map = {
            "IDLE":      "#94a3b8",
            "SEARCH":    "#e67e22",
            "ACQUIRE":   "#f39c12",
            "LOCKED":    "#16a085",
            "COAST":     "#3498db",
            "LOST":      "#e74c3c",
            "REACQUIRE": "#9b59b6",
        }
        bg = color_map.get(state_name, "#34495e") if active else "transparent"
        fg = "#ffffff" if active else "#64748b"
        border = bg if active else "#334155"
        
        return f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 2px solid {border};
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 10px;
                font-weight: bold;
            }}
        """

    def set_state(self, current_state: str):
        for st, lbl in self.labels.items():
            is_active = (st == current_state)
            lbl.setStyleSheet(self._get_style(is_active, st))
