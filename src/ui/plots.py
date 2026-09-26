import pyqtgraph as pg
import numpy as np

class RealTimePlot(pg.PlotWidget):
    def __init__(self, title, y_label, max_points=300):
        super().__init__()
        
        # ══════════════════════════════════════════════════════════════
        # Apply Dark Theme Styling for pyqtgraph
        # ══════════════════════════════════════════════════════════════
        self.setBackground('#1e1e1e')  # Match QSS dark background
        
        self.setTitle(title, color='#4fc3f7', size='11pt')
        self.setLabel('left', y_label, color='#d4d4d4', **{'font-size': '10pt'})
        self.setLabel('bottom', "Time (frames)", color='#d4d4d4', **{'font-size': '10pt'})
        
        # Grid styling (dark theme)
        self.showGrid(x=True, y=True, alpha=0.3)
        
        # Axis styling
        axis_pen = pg.mkPen(color='#555', width=1)
        self.getAxis('left').setPen(axis_pen)
        self.getAxis('bottom').setPen(axis_pen)
        self.getAxis('left').setTextPen('#d4d4d4')
        self.getAxis('bottom').setTextPen('#d4d4d4')
        
        self.max_points = max_points
        self.data = []
        
        # Bright cyan curve for visibility on dark background
        self.curve = self.plot(pen=pg.mkPen('#00e5ff', width=2))
        
    def update_value(self, value):
        self.data.append(value)
        if len(self.data) > self.max_points:
            self.data.pop(0)
            
        self.curve.setData(self.data)
        
    def reset(self):
        self.data.clear()
        self.curve.setData(self.data)
