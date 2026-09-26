"""
world_view.py — Enhanced 2000×2000 world visualization widget

Renders the complete world view with:
- Beacon position (large red circle with velocity arrow)
- Platform position (blue circle, if enabled)
- Camera FOV rectangle (color-coded by state, corner markers)
- Gimbal center (large crosshair with circle)
- Track history trail (yellow line, last 200 positions)
- Velocity arrows (cyan for beacon, yellow for gimbal)
- Grid overlay with coordinate labels (400px spacing)
- Enhanced legend with explanations
- Real-time stats overlay (positions, distance, speed)
- State banner at top

Updates at 30 FPS for real-time monitoring and debugging.
"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
import numpy as np
import cv2


class WorldViewWidget(QLabel):
    """
    Renders the full 2000×2000 world view scaled to fit display.
    
    Shows global scene context with beacon trajectory, camera FOV,
    and tracking history for spatial awareness and debugging.
    """
    
    def __init__(self, world_size=(2000, 2000), fov_deg=(4.0, 3.0)):
        super().__init__()
        self.world_w, self.world_h = world_size
        self.fov_w_deg, self.fov_h_deg = fov_deg
        
        # Display size (compact, scaled down from 2000×2000)
        self.display_size = (400, 400)  # Compact square display
        self.scale_x = self.display_size[0] / self.world_w
        self.scale_y = self.display_size[1] / self.world_h
        
        # Track history buffer (last 200 positions for cleaner trails)
        self.track_history = []
        self.max_history = 200
        
        # NEW: Velocity tracking for motion arrows
        self.prev_beacon_pos = None
        self.prev_gimbal_pos = None
        self.beacon_velocity = (0, 0)
        self.gimbal_velocity = (0, 0)
        
        self.tracking_state = "IDLE"
        
        self.setMinimumSize(300, 300)
        self.setStyleSheet("background: #1a1a1a; border: 2px solid #444;")
        self.setAlignment(Qt.AlignCenter)
        
        # Initialize with blank canvas
        self._render_blank()
        
    def _render_blank(self, message="World View"):
        """Render initial blank canvas."""
        canvas = np.zeros((self.display_size[1], self.display_size[0], 3), dtype=np.uint8)
        canvas[:, :] = (26, 26, 26)  # Dark background
        
        # Add message in center
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        text_size = cv2.getTextSize(message, font, font_scale, thickness)[0]
        text_x = (self.display_size[0] - text_size[0]) // 2
        
        cv2.putText(canvas, message, 
                   (text_x, self.display_size[1]//2 - 10), 
                   font, font_scale, (100, 100, 100), thickness, cv2.LINE_AA)
        
        if message == "World View":
            cv2.putText(canvas, f"{self.world_w}x{self.world_h} space", 
                       (self.display_size[0]//2 - 70, self.display_size[1]//2 + 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1, cv2.LINE_AA)
        
        # Draw world boundary box
        border = 20
        cv2.rectangle(canvas, (border, border), 
                     (self.display_size[0] - border, self.display_size[1] - border),
                     (50, 50, 50), 1)
        
        self._display_canvas(canvas)
        
    def update_world(self, beacon_x, beacon_y, gimbal_x, gimbal_y, 
                     fov_px=(640, 480), platform_x=None, platform_y=None,
                     tracking_state="IDLE", platform_is_moving=False,
                     distractors=None, beacon_w=10, beacon_h=10):
        """
        Update world visualization with enhanced visuals.
        
        Args:
            beacon_x, beacon_y: Beacon position in world coords
            gimbal_x, gimbal_y: Camera center in world coords
            fov_px: Camera FOV size in pixels (viewport resolution)
            platform_x, platform_y: Platform position (optional)
            tracking_state: Current tracking state (for FOV color and banner)
            platform_is_moving: Whether platform is actually moving (hide if static)
            distractors: List of distractor tuples (x, y, w, h)
            beacon_w, beacon_h: Size of primary beacon in world coords
        """
        self.tracking_state = tracking_state
        
        # Calculate velocities (change from previous frame)
        if self.prev_beacon_pos:
            self.beacon_velocity = (beacon_x - self.prev_beacon_pos[0], 
                                   beacon_y - self.prev_beacon_pos[1])
        if self.prev_gimbal_pos:
            self.gimbal_velocity = (gimbal_x - self.prev_gimbal_pos[0],
                                   gimbal_y - self.prev_gimbal_pos[1])
        
        self.prev_beacon_pos = (beacon_x, beacon_y)
        self.prev_gimbal_pos = (gimbal_x, gimbal_y)
        
        # Create blank canvas
        canvas = np.zeros((self.display_size[1], self.display_size[0], 3), dtype=np.uint8)
        canvas[:, :] = (26, 26, 26)  # Dark background
        
        # Draw state banner at top
        self._draw_state_banner(canvas, tracking_state)
        
        # Draw grid overlay (400px spacing in world coords)
        self._draw_grid_enhanced(canvas, spacing=400)
        
        # World-to-display coordinate conversion
        def to_display(wx, wy):
            dx = int(wx * self.scale_x)
            dy = int(wy * self.scale_y)
            return (dx, dy)
        
        # Add beacon to track history
        self.track_history.append((beacon_x, beacon_y))
        if len(self.track_history) > self.max_history:
            self.track_history.pop(0)
        
        # Draw track history trail (yellow line with fade effect)
        if len(self.track_history) > 1:
            points = np.array([to_display(x, y) for x, y in self.track_history], dtype=np.int32)
            cv2.polylines(canvas, [points], isClosed=False, color=(0, 200, 255), thickness=2)
        
        # Determine FOV color based on tracking state
        fov_color = self._get_fov_color(tracking_state)
        
        # Draw camera FOV rectangle with corner markers
        fov_w_px, fov_h_px = fov_px
        fov_world_w = fov_w_px  # FOV in world pixels (1:1 mapping)
        fov_world_h = fov_h_px
        top_left = to_display(gimbal_x - fov_world_w/2, gimbal_y - fov_world_h/2)
        bottom_right = to_display(gimbal_x + fov_world_w/2, gimbal_y + fov_world_h/2)
        
        # FOV rectangle (thicker)
        cv2.rectangle(canvas, top_left, bottom_right, color=fov_color, thickness=4)
        
        # Corner markers for FOV
        corner_size = 8
        for corner in [top_left, (bottom_right[0], top_left[1]), 
                      bottom_right, (top_left[0], bottom_right[1])]:
            cv2.circle(canvas, corner, radius=corner_size, color=fov_color, thickness=2)
        
        # Draw platform position ONLY if it's actually moving (blue circle)
        if platform_is_moving and platform_x is not None and platform_y is not None:
            platform_pos = to_display(platform_x, platform_y)
            cv2.circle(canvas, platform_pos, radius=6, color=(255, 100, 0), thickness=-1)
            cv2.circle(canvas, platform_pos, radius=9, color=(255, 150, 0), thickness=2)
            # Label it
            cv2.putText(canvas, "Platform", 
                       (platform_pos[0] - 20, platform_pos[1] - 12),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 150, 0), 1, cv2.LINE_AA)
        
        # Draw Distractors
        if distractors is None:
            distractors = []
        for i, (dx, dy, dw, dh) in enumerate(distractors):
            d_pos = to_display(dx, dy)
            rect_w = max(2, int(dw * self.scale_x))
            rect_h = max(2, int(dh * self.scale_y))
            top_left = (d_pos[0] - rect_w // 2, d_pos[1] - rect_h // 2)
            bottom_right = (d_pos[0] + rect_w // 2, d_pos[1] + rect_h // 2)
            
            # Orange filled rect (BGR: 0, 165, 255)
            cv2.rectangle(canvas, top_left, bottom_right, (0, 165, 255), -1)
            # Label
            cv2.putText(canvas, f"D{i+1} {dw}x{dh}", (d_pos[0] - 20, d_pos[1] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 165, 255), 1, cv2.LINE_AA)
        
        # Draw beacon position (Cyan filled rect, accurate WxH)
        beacon_pos = to_display(beacon_x, beacon_y)
        rect_w = max(2, int(beacon_w * self.scale_x))
        rect_h = max(2, int(beacon_h * self.scale_y))
        top_left = (beacon_pos[0] - rect_w // 2, beacon_pos[1] - rect_h // 2)
        bottom_right = (beacon_pos[0] + rect_w // 2, beacon_pos[1] + rect_h // 2)
        
        # Cyan filled rect (BGR: 255, 255, 0)
        cv2.rectangle(canvas, top_left, bottom_right, (255, 255, 0), -1)
        
        # Lock ring
        ring_tl = (top_left[0] - 2, top_left[1] - 2)
        ring_br = (bottom_right[0] + 2, bottom_right[1] + 2)
        if tracking_state == "LOCKED":
            cv2.rectangle(canvas, ring_tl, ring_br, (0, 255, 0), 2)  # Green ring
        elif tracking_state in ["SEARCH", "LOST"]:
            self._draw_dashed_rectangle(canvas, ring_tl, ring_br, (0, 0, 255), 1)  # Red dashed ring
            
        # Primary beacon label
        cv2.putText(canvas, f"TARGET {beacon_w}x{beacon_h}", (beacon_pos[0] - 30, beacon_pos[1] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 0), 1, cv2.LINE_AA)
        
        # Draw beacon velocity arrow
        self._draw_velocity_arrow(canvas, beacon_pos, self.beacon_velocity, 
                                 color=(0, 255, 255), scale=2.0)
        
        # Draw gimbal/camera center (LARGE crosshair + circle)
        gimbal_pos = to_display(gimbal_x, gimbal_y)
        cv2.drawMarker(canvas, gimbal_pos, color=fov_color, 
                      markerType=cv2.MARKER_CROSS, markerSize=16, thickness=2)
        cv2.circle(canvas, gimbal_pos, radius=4, color=fov_color, thickness=-1)
        
        # Draw gimbal velocity arrow
        self._draw_velocity_arrow(canvas, gimbal_pos, self.gimbal_velocity,
                                 color=(0, 255, 0), scale=2.0)
        
        # Draw world boundary (white thin border)
        cv2.rectangle(canvas, (0, 0), 
                     (self.display_size[0]-1, self.display_size[1]-1), 
                     color=(60, 60, 60), thickness=1)
        
        # Add enhanced legend
        self._draw_legend_enhanced(canvas, tracking_state, show_platform=platform_is_moving)
        
        # Add real-time stats overlay
        self._draw_stats_overlay(canvas, beacon_x, beacon_y, gimbal_x, gimbal_y)
        
        # Display
        self._display_canvas(canvas)
    
    def _draw_grid(self, canvas, spacing=500):
        """Draw subtle grid overlay with specified spacing in world coordinates."""
        # Vertical lines
        for wx in range(0, self.world_w + 1, spacing):
            dx = int(wx * self.scale_x)
            cv2.line(canvas, (dx, 0), (dx, self.display_size[1]), 
                    color=(35, 35, 35), thickness=1)  # More subtle
        
        # Horizontal lines
        for wy in range(0, self.world_h + 1, spacing):
            dy = int(wy * self.scale_y)
            cv2.line(canvas, (0, dy), (self.display_size[0], dy), 
                    color=(35, 35, 35), thickness=1)  # More subtle
    
    def _draw_grid_enhanced(self, canvas, spacing=400):
        """Draw enhanced grid with coordinate labels."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.3
        thickness = 1
        
        # Vertical lines with labels
        for wx in range(0, self.world_w + 1, spacing):
            dx = int(wx * self.scale_x)
            cv2.line(canvas, (dx, 0), (dx, self.display_size[1]), 
                    color=(40, 40, 40), thickness=1)
            # Label at bottom (every other line to avoid clutter)
            if wx % (spacing * 2) == 0 and dx > 10 and dx < self.display_size[0] - 20:
                cv2.putText(canvas, str(wx), (dx - 10, self.display_size[1] - 3),
                           font, font_scale, (60, 60, 60), thickness, cv2.LINE_AA)
        
        # Horizontal lines with labels
        for wy in range(0, self.world_h + 1, spacing):
            dy = int(wy * self.scale_y)
            cv2.line(canvas, (0, dy), (self.display_size[0], dy), 
                    color=(40, 40, 40), thickness=1)
            # Label at left (every other line)
            if wy % (spacing * 2) == 0 and dy > 15 and dy < self.display_size[1] - 10:
                cv2.putText(canvas, str(wy), (3, dy + 4),
                           font, font_scale, (60, 60, 60), thickness, cv2.LINE_AA)
        
        # Center crosshair at (1000, 1000)
        center = (int(self.world_w/2 * self.scale_x), int(self.world_h/2 * self.scale_y))
        cv2.drawMarker(canvas, center, color=(50, 50, 50), 
                      markerType=cv2.MARKER_TILTED_CROSS, markerSize=12, thickness=1)
    
    def _get_fov_color(self, state):
        """Get FOV rectangle color based on tracking state."""
        color_map = {
            "LOCKED":    (0, 255, 0),    # Green
            "ACQUIRE":   (0, 255, 255),  # Yellow
            "COAST":     (0, 165, 255),  # Orange
            "SEARCH":    (0, 100, 255),  # Red-orange
            "REACQUIRE": (255, 0, 255),  # Magenta
            "LOST":      (0, 0, 255),    # Red
            "IDLE":      (100, 100, 100) # Gray
        }
        return color_map.get(state, (100, 100, 100))
    
    def _draw_velocity_arrow(self, canvas, pos, velocity, color, scale=1.0):
        """Draw velocity arrow showing movement direction and magnitude."""
        vx, vy = velocity
        
        # Scale velocity to display coords
        vx_display = vx * self.scale_x * scale
        vy_display = vy * self.scale_y * scale
        
        # Only draw if velocity is significant
        mag = np.hypot(vx_display, vy_display)
        if mag < 2.0:  # Too small to show
            return
        
        # Limit arrow length for readability
        max_len = 30
        if mag > max_len:
            vx_display = (vx_display / mag) * max_len
            vy_display = (vy_display / mag) * max_len
        
        end_pos = (int(pos[0] + vx_display), int(pos[1] + vy_display))
        
        cv2.arrowedLine(canvas, pos, end_pos, color, thickness=2, tipLength=0.3)
    
    def _draw_state_banner(self, canvas, state):
        """Draw state banner at top with explanation."""
        banner_h = 22
        banner_color = self._get_fov_color(state)
        
        # Semi-transparent banner background
        overlay = canvas.copy()
        cv2.rectangle(overlay, (0, 0), (self.display_size[0], banner_h), 
                     banner_color, -1)
        cv2.addWeighted(overlay, 0.3, canvas, 0.7, 0, canvas)
        
        # State text with explanation
        state_explanations = {
            "LOCKED": "Tracking Target ✓",
            "ACQUIRE": "Acquiring Lock...",
            "COAST": "Coasting (prediction)",
            "SEARCH": "Scanning for Target",
            "REACQUIRE": "Reacquiring...",
            "LOST": "Target Lost - Searching",
            "IDLE": "System Idle"
        }
        text = f"{state}: {state_explanations.get(state, '')}"
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 0.45, 1)[0]
        text_x = (self.display_size[0] - text_size[0]) // 2
        
        cv2.putText(canvas, text, (text_x, 15), font, 0.45, 
                   (255, 255, 255), 1, cv2.LINE_AA)
    
    def _draw_legend(self, canvas, state):
        """Draw compact legend with element colors and current state."""
        y_offset = 15
        x_offset = 8
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.35  # Smaller for compact display
        thickness = 1
        line_height = 14
        
        # Legend entries with symbols
        legend_items = [
            ("● Beacon", (0, 100, 255)),
            ("□ Camera FOV", self._get_fov_color(state)),
            ("— Track Trail", (0, 255, 255)),
        ]
        
        for i, (label, color) in enumerate(legend_items):
            y_pos = y_offset + i * line_height
            cv2.putText(canvas, label, (x_offset, y_pos), 
                       font, font_scale, color, thickness, cv2.LINE_AA)
        
        # State indicator at top right
        state_text = f"{state}"
        text_size = cv2.getTextSize(state_text, font, 0.4, 1)[0]
        state_x = self.display_size[0] - text_size[0] - 10
        cv2.putText(canvas, state_text, (state_x, 15), 
                   font, 0.4, self._get_fov_color(state), 1, cv2.LINE_AA)
        
        # World size indicator at bottom
        world_text = f"{self.world_w}×{self.world_h}px"
        cv2.putText(canvas, world_text, 
                   (10, self.display_size[1] - 8), 
                   font, font_scale, (100, 100, 100), thickness, cv2.LINE_AA)
    
    def _draw_legend_enhanced(self, canvas, state, show_platform=False):
        """Draw enhanced legend with explanations."""
        y_offset = 30  # Below state banner
        x_offset = 6
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.32
        thickness = 1
        line_height = 12
        
        # Enhanced legend entries (conditionally include platform)
        legend_items = [
            ("● Beacon (target)", (0, 100, 255)),
            ("□ Camera FOV", self._get_fov_color(state)),
            ("+ Gimbal center", self._get_fov_color(state)),
            ("— Trail history", (0, 200, 255)),
            ("→ Velocity", (0, 255, 255)),
        ]
        
        # Only show platform in legend if it's moving
        if show_platform:
            legend_items.insert(1, ("◉ Platform (moving)", (255, 150, 0)))
        
        for i, (label, color) in enumerate(legend_items):
            y_pos = y_offset + i * line_height
            cv2.putText(canvas, label, (x_offset, y_pos), 
                       font, font_scale, color, thickness, cv2.LINE_AA)
    
    def _draw_stats_overlay(self, canvas, beacon_x, beacon_y, gimbal_x, gimbal_y):
        """Draw real-time stats overlay at bottom."""
        y_start = self.display_size[1] - 60
        x_offset = 6
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.32
        thickness = 1
        line_height = 12
        
        # Calculate distance
        distance = np.hypot(beacon_x - gimbal_x, beacon_y - gimbal_y)
        
        # Calculate speeds (magnitude of velocity)
        beacon_speed = np.hypot(self.beacon_velocity[0], self.beacon_velocity[1])
        
        stats = [
            f"Beacon: ({int(beacon_x)}, {int(beacon_y)})",
            f"Gimbal: ({int(gimbal_x)}, {int(gimbal_y)})",
            f"Distance: {int(distance)} px",
            f"Beacon speed: {beacon_speed:.1f} px/f",
        ]
        
        for i, stat in enumerate(stats):
            y_pos = y_start + i * line_height
            cv2.putText(canvas, stat, (x_offset, y_pos),
                       font, font_scale, (150, 150, 150), thickness, cv2.LINE_AA)
    
    def _display_canvas(self, canvas):
        """Convert numpy array to QPixmap and display."""
        h, w, ch = canvas.shape
        bytes_per_line = ch * w
        qimg = QImage(canvas.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pix = QPixmap.fromImage(qimg)
        self.setPixmap(pix)
    
    def clear_history(self, message="World View"):
        """Clear track history trail and reset velocities."""
        self.track_history = []
        self.prev_beacon_pos = None
        self.prev_gimbal_pos = None
        self.beacon_velocity = (0, 0)
        self.gimbal_velocity = (0, 0)
        self._render_blank(message)
    def _draw_dashed_rectangle(self, img, pt1, pt2, color, thickness=1, dash_length=4):
        """Draws a dashed rectangle."""
        x1, y1 = pt1
        x2, y2 = pt2
        # Top
        for i in range(x1, x2, dash_length * 2):
            cv2.line(img, (i, y1), (min(i + dash_length, x2), y1), color, thickness)
        # Bottom
        for i in range(x1, x2, dash_length * 2):
            cv2.line(img, (i, y2), (min(i + dash_length, x2), y2), color, thickness)
        # Left
        for i in range(y1, y2, dash_length * 2):
            cv2.line(img, (x1, i), (x1, min(i + dash_length, y2)), color, thickness)
        # Right
        for i in range(y1, y2, dash_length * 2):
            cv2.line(img, (x2, i), (x2, min(i + dash_length, y2)), color, thickness)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep aspect ratio 1:1 to prevent squashing
        size = min(self.width(), self.height())
        if size > 50:
            self.display_size = (size, size)
            self.scale_x = self.display_size[0] / self.world_w
            self.scale_y = self.display_size[1] / self.world_h

    def mouseDoubleClickEvent(self, event):
        """Toggle full screen / popout view."""
        if self.isWindow():
            # Return to normal
            self.setWindowFlags(Qt.Widget)
            self.showNormal()
            if hasattr(self, 'parent_widget') and self.parent_widget:
                self.setParent(self.parent_widget)
                self.parent_layout.addWidget(self)
        else:
            # Go full screen popout
            self.parent_widget = self.parent()
            self.parent_layout = self.parent_widget.layout() if self.parent_widget else None
            self.setParent(None)
            self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
            self.setWindowTitle("LaserPAT - Full Screen World View (Double Click to return)")
            self.showMaximized()
