import numpy as np
import cv2
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt

class WorldView3DWidget(QLabel):
    def __init__(self, world_w=2000, world_h=2000, display_size=(600, 600)):
        super().__init__()
        self.world_w = world_w
        self.world_h = world_h
        
        # Fixed internal rendering resolution to prevent lag
        self.render_w = 800
        self.render_h = 600
        self.display_size = (self.render_w, self.render_h)
        
        self.setMinimumSize(400, 400)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b;")

        
        # 3D projection parameters - SIDEWAYS VIEW (looking from the side)
        # Imagine camera positioned to the side, looking across the scene
        self.camera_distance = 3500  # Distance from scene center
        self.camera_height = 600     # Camera elevation
        
        # Rotation angles for sideways perspective
        self.pitch = np.radians(20)   # Slight tilt down (20° from horizontal)
        self.yaw = np.radians(65)     # View from side angle (65° gives nice perspective)
        
        self.scale = 0.16  # Slightly larger scale for display
        self.offset_x = self.render_w / 2
        self.offset_y = self.render_h / 2 + 100  # Push scene down for better composition
        
        # Track history for motion trails
        self.beacon_trail = []
        self.max_trail_length = 50
        
        self._render_blank()

    def project_3d_to_2d(self, x, y, z):
        """
        Enhanced 3D to 2D projection with sideways perspective.
        
        Coordinate system:
        - X: Left to right (0 → world_w)
        - Y: Near to far (0 → world_h) 
        - Z: Ground to sky (0 → up)
        """
        # Center world around origin for rotation
        cx = x - self.world_w / 2
        cy = y - self.world_h / 2
        cz = z
        
        # Apply yaw rotation (rotate around Z axis for side view)
        x_yaw = cx * np.cos(self.yaw) + cy * np.sin(self.yaw)
        y_yaw = -cx * np.sin(self.yaw) + cy * np.cos(self.yaw)
        z_yaw = cz
        
        # Apply pitch rotation (tilt camera down)
        x_final = x_yaw
        y_final = y_yaw * np.cos(self.pitch) - z_yaw * np.sin(self.pitch)
        z_final = y_yaw * np.sin(self.pitch) + z_yaw * np.cos(self.pitch)
        
        # Add perspective (optional - makes it look more 3D)
        # Farther objects get slightly smaller
        perspective_factor = 1.0 + (y_final / 3000.0)
        
        # Project to 2D screen coordinates
        px = int(x_final * self.scale / perspective_factor + self.offset_x)
        py = int(-z_final * self.scale / perspective_factor + self.offset_y)  # Negative Z because screen Y goes down
        
        return (px, py)

    def update_world_3d(self, beacon_x, beacon_y, gimbal_x, gimbal_y, 
                        fov_px=(640, 480), platform_x=None, platform_y=None,
                        tracking_state="IDLE", distractors=None, beacon_w=10, beacon_h=10):
        """
        Render beautiful sideways 3D perspective view.
        """
        # Create canvas with solid dark slate background (Asteria-like)
        canvas = np.zeros((self.render_h, self.render_w, 3), dtype=np.uint8)
        
        # Base background: Deep slate (#0f172a) -> BGR: (42, 23, 15)
        canvas[:] = (42, 23, 15)
        
        # Subtle glowing horizon
        horizon_y = int(self.render_h * 0.4)
        for y in range(horizon_y - 100, horizon_y + 150):
            dist = abs(y - horizon_y)
            intensity = max(0, 30 - int(dist * 0.2))
            canvas[y, :] = (42 + intensity, 23 + intensity, 15 + intensity)

        
        # === 1. Draw Ground Plane with Grid ===
        self._draw_ground_grid(canvas)
        
        # === 2. Draw Beacon Motion Trail (if available) ===
        self.beacon_trail.append((beacon_x, beacon_y))
        if len(self.beacon_trail) > self.max_trail_length:
            self.beacon_trail.pop(0)
        
        if len(self.beacon_trail) > 1:
            trail_points = []
            for i, (tx, ty) in enumerate(self.beacon_trail):
                pt = self.project_3d_to_2d(tx, ty, 5)  # Slightly above ground
                trail_points.append(pt)
            
            # Draw trail with fading alpha effect
            for i in range(len(trail_points) - 1):
                alpha = (i + 1) / len(trail_points)  # Fade in along trail
                thickness = max(1, int(alpha * 3))
                color_intensity = int(alpha * 200)
                cv2.line(canvas, trail_points[i], trail_points[i+1], 
                        (color_intensity, color_intensity, 255), thickness)
        
        # === 3. Draw Distractors (if present) ===
        if distractors:
            for dx, dy, dw, dh in distractors:
                self._draw_beacon_3d(canvas, dx, dy, dw, dh, 
                                    color=(0, 140, 255),  # Orange
                                    label="DISTRACTOR",
                                    height=150)
        
        # === 4. Draw Primary Beacon (TARGET) ===
        self._draw_beacon_3d(canvas, beacon_x, beacon_y, beacon_w, beacon_h,
                            color=(0, 255, 255),  # Bright cyan
                            label="TARGET",
                            height=250,
                            glow=True)
        
        # === 5. Draw Platform and Camera Setup ===
        if platform_x is None: platform_x = self.world_w / 2
        if platform_y is None: platform_y = self.world_h / 2
        
        camera_height = 400  # Camera mounted on mast at this height
        self._draw_camera_system(canvas, platform_x, platform_y, camera_height, tracking_state)
        
        # === 6. Draw Camera FOV Projection ===
        self._draw_fov_frustum(canvas, gimbal_x, gimbal_y, fov_px, camera_height, tracking_state)
        
        # === 7. Add Labels and Info ===
        self._draw_labels_and_info(canvas, tracking_state, beacon_x, beacon_y, gimbal_x, gimbal_y)
        
        # === 8. Add Ambient Lighting Effects ===
        self._add_atmosphere(canvas)
        
        self._display_canvas(canvas)
    
    def _draw_ground_grid(self, canvas):
        """Draw a perspective grid on the ground plane."""
        grid_spacing = 400  # Larger spacing for cleaner look
        
        # Grid lines (Slate/cyan tint)
        grid_color = (60, 45, 30)
        
        # Draw grid lines in both directions
        for x in range(0, self.world_w + 1, grid_spacing):
            pt1 = self.project_3d_to_2d(x, 0, 0)
            pt2 = self.project_3d_to_2d(x, self.world_h, 0)
            cv2.line(canvas, pt1, pt2, grid_color, 1, cv2.LINE_AA)
        
        for y in range(0, self.world_h + 1, grid_spacing):
            pt1 = self.project_3d_to_2d(0, y, 0)
            pt2 = self.project_3d_to_2d(self.world_w, y, 0)
            cv2.line(canvas, pt1, pt2, grid_color, 1, cv2.LINE_AA)
        
        # Draw coordinate axes (Modern colors)
        origin = self.project_3d_to_2d(0, 0, 0)
        x_axis = self.project_3d_to_2d(800, 0, 0)
        y_axis = self.project_3d_to_2d(0, 800, 0)
        
        cv2.arrowedLine(canvas, origin, x_axis, (50, 50, 255), 2, tipLength=0.05)  # Red X
        cv2.arrowedLine(canvas, origin, y_axis, (200, 200, 50), 2, tipLength=0.05)  # Cyan Y
        
        # Label axes
        cv2.putText(canvas, "X", (x_axis[0] + 5, x_axis[1]), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, "Y", (y_axis[0] + 5, y_axis[1]), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 50), 1, cv2.LINE_AA)
    
    def _draw_beacon_3d(self, canvas, x, y, w, h, color, label, height, glow=False):
        """Draw a beacon with vertical pillar and glow effect."""
        # Ground position
        ground_pt = self.project_3d_to_2d(x, y, 0)
        
        # Top of beacon pillar
        top_pt = self.project_3d_to_2d(x, y, height)
        
        # Draw vertical pillar (thin line)
        cv2.line(canvas, ground_pt, top_pt, (color[0]//3, color[1]//3, color[2]//3), 2, cv2.LINE_AA)
        
        # Draw beacon marker at top (larger circle)
        beacon_radius = max(4, int((w + h) / 4))
        
        # Glow effect for primary target
        if glow:
            cv2.circle(canvas, top_pt, beacon_radius + 8, 
                      (color[0]//4, color[1]//4, color[2]//4), -1, cv2.LINE_AA)
            cv2.circle(canvas, top_pt, beacon_radius + 4, 
                      (color[0]//2, color[1]//2, color[2]//2), -1, cv2.LINE_AA)
        
        # Main beacon
        cv2.circle(canvas, top_pt, beacon_radius, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, top_pt, beacon_radius, (255, 255, 255), 1, cv2.LINE_AA)  # White outline
        
        # Draw ground footprint (shadow)
        cv2.circle(canvas, ground_pt, beacon_radius - 1, (20, 20, 20), -1, cv2.LINE_AA)
        
        # Label
        label_pos = (top_pt[0] - len(label) * 3, top_pt[1] - beacon_radius - 8)
        cv2.putText(canvas, label, label_pos,
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    
    def _draw_camera_system(self, canvas, platform_x, platform_y, camera_height, state):
        """Draw platform and camera system with mast."""
        # Platform base on ground
        plat_ground = self.project_3d_to_2d(platform_x, platform_y, 0)
        
        # Camera position at height
        cam_pos = self.project_3d_to_2d(platform_x, platform_y, camera_height)
        
        # Draw mast (thick line with gradient effect)
        cv2.line(canvas, plat_ground, cam_pos, (80, 80, 80), 3, cv2.LINE_AA)
        cv2.line(canvas, plat_ground, cam_pos, (120, 120, 120), 1, cv2.LINE_AA)  # Highlight
        
        # Draw platform base (larger circle with rings)
        cv2.circle(canvas, plat_ground, 12, (40, 40, 40), -1, cv2.LINE_AA)  # Shadow
        cv2.circle(canvas, plat_ground, 10, (255, 160, 60), -1, cv2.LINE_AA)  # Orange platform
        cv2.circle(canvas, plat_ground, 10, (255, 200, 100), 2, cv2.LINE_AA)  # Highlight ring
        cv2.circle(canvas, plat_ground, 7, (200, 120, 40), 1, cv2.LINE_AA)   # Inner detail
        
        # Draw camera body (larger with detail)
        cv2.circle(canvas, cam_pos, 9, (40, 40, 40), -1, cv2.LINE_AA)  # Shadow
        cv2.circle(canvas, cam_pos, 8, (180, 180, 180), -1, cv2.LINE_AA)  # Camera body
        cv2.circle(canvas, cam_pos, 8, (220, 220, 220), 1, cv2.LINE_AA)  # Outline
        cv2.circle(canvas, cam_pos, 4, (80, 80, 80), -1, cv2.LINE_AA)  # Lens
        
        # State indicator light on camera
        state_color = self._get_state_color(state)
        cv2.circle(canvas, (cam_pos[0] + 6, cam_pos[1] - 6), 3, state_color, -1, cv2.LINE_AA)
        
        # Labels
        cv2.putText(canvas, "PLATFORM", (plat_ground[0] - 25, plat_ground[1] + 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 180, 80), 1, cv2.LINE_AA)
        cv2.putText(canvas, "CAMERA", (cam_pos[0] + 12, cam_pos[1] + 3),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1, cv2.LINE_AA)
    
    def _draw_fov_frustum(self, canvas, gimbal_x, gimbal_y, fov_px, camera_height, state):
        """Draw camera FOV frustum from camera to ground."""
        fw, fh = fov_px
        
        # FOV corners on ground
        corners = [
            (gimbal_x - fw/2, gimbal_y - fh/2),
            (gimbal_x + fw/2, gimbal_y - fh/2),
            (gimbal_x + fw/2, gimbal_y + fh/2),
            (gimbal_x - fw/2, gimbal_y + fh/2)
        ]
        
        # Get camera position (use gimbal center at camera height)
        cam_pos = self.project_3d_to_2d(gimbal_x, gimbal_y, camera_height)
        
        fov_color = self._get_state_color(state)
        
        # Draw frustum lines from camera to ground corners (semi-transparent effect)
        for cx, cy in corners:
            corner_pt = self.project_3d_to_2d(cx, cy, 0)
            cv2.line(canvas, cam_pos, corner_pt, 
                    (fov_color[0]//3, fov_color[1]//3, fov_color[2]//3), 1, cv2.LINE_AA)
        
        # Draw FOV footprint on ground (quadrilateral)
        ground_corners = [self.project_3d_to_2d(cx, cy, 0) for cx, cy in corners]
        pts = np.array(ground_corners, np.int32).reshape((-1, 1, 2))
        
        # Filled polygon with transparency effect (draw darker version first)
        cv2.fillPoly(canvas, [pts], (fov_color[0]//6, fov_color[1]//6, fov_color[2]//6), cv2.LINE_AA)
        
        # FOV outline (thicker, brighter)
        cv2.polylines(canvas, [pts], True, fov_color, 2, cv2.LINE_AA)
        
        # Corner markers
        for pt in ground_corners:
            cv2.circle(canvas, pt, 3, fov_color, -1, cv2.LINE_AA)
    
    def _get_state_color(self, state):
        """Get color for tracking state."""
        color_map = {
            "LOCKED":    (0, 255, 0),     # Green
            "ACQUIRE":   (0, 255, 255),   # Yellow
            "COAST":     (0, 200, 255),   # Orange
            "SEARCH":    (0, 100, 255),   # Red-orange
            "REACQUIRE": (200, 0, 255),   # Magenta
            "LOST":      (0, 0, 255),     # Red
            "IDLE":      (100, 100, 100)  # Gray
        }
        return color_map.get(state, (100, 100, 100))
    
    def _draw_labels_and_info(self, canvas, state, beacon_x, beacon_y, gimbal_x, gimbal_y):
        """Draw title, state, and info overlay."""
        # Title bar (modern)
        cv2.putText(canvas, "3D ISOMETRIC VIEW", (15, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        
        # State badge
        state_color = self._get_state_color(state)
        state_text = f" {state} "
        text_size = cv2.getTextSize(state_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
        badge_x = self.render_w - text_size[0] - 25
        
        # Glassmorphic badge background
        overlay = canvas.copy()
        cv2.rectangle(overlay, (badge_x - 5, 10), 
                     (badge_x + text_size[0] + 5, 30), (30, 41, 59), -1)
        cv2.addWeighted(overlay, 0.8, canvas, 0.2, 0, canvas)
        cv2.rectangle(canvas, (badge_x - 5, 10), 
                     (badge_x + text_size[0] + 5, 30), state_color, 1, cv2.LINE_AA)
        cv2.putText(canvas, state_text, (badge_x, 24),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, state_color, 1, cv2.LINE_AA)
        
        # Info panel at bottom
        distance = np.hypot(beacon_x - gimbal_x, beacon_y - gimbal_y)
        info_text = f"Target: ({int(beacon_x)}, {int(beacon_y)})  |  Distance: {int(distance)}px"
        cv2.putText(canvas, info_text, (15, self.render_h - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (148, 163, 184), 1, cv2.LINE_AA)
    
    def _add_atmosphere(self, canvas):
        """Add subtle atmospheric effects for depth."""
        rows, cols = canvas.shape[:2]
        
        # Initialize or update cache if size changed
        if not hasattr(self, '_vignette_cache') or self._vignette_cache.shape[:2] != (rows, cols):
            X, Y = np.meshgrid(np.arange(cols), np.arange(rows))
            center_x, center_y = cols / 2, rows / 2
            
            # Distance from center
            dist_from_center = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
            max_dist = np.sqrt(center_x**2 + center_y**2)
            
            # Vignette mask (1.0 at center, 0.85 at edges)
            vignette = 1.0 - (dist_from_center / max_dist) * 0.15
            vignette = np.clip(vignette, 0.85, 1.0)
            
            # Pre-expand to 3 channels for faster broadcasting
            self._vignette_cache = np.stack([vignette]*3, axis=2)
            
        # Apply cached vignette using fast vectorization
        np.multiply(canvas, self._vignette_cache, out=canvas, casting='unsafe')
    
    def clear_trail(self):
        """Clear the beacon motion trail."""
        self.beacon_trail = []
        
    def _display_canvas(self, canvas):
        h, w, ch = canvas.shape
        bytes_per_line = ch * w
        qimg = QImage(canvas.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pix = QPixmap.fromImage(qimg)
        # Scale to fit widget size smoothly
        scaled_pix = pix.scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled_pix)

    def _render_blank(self):
        canvas = np.zeros((self.render_h, self.render_w, 3), dtype=np.uint8)
        canvas[:] = (42, 23, 15)
        cv2.putText(canvas, "3D ISOMETRIC VIEW", 
                   (self.render_w//2 - 80, self.render_h//2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(canvas, "Start Tracking (Platform Moving) to begin", 
                   (self.render_w//2 - 120, self.render_h//2 + 25), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 116, 139), 1, cv2.LINE_AA)
        self._display_canvas(canvas)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Do not change internal render resolution to prevent lag
        # Just update the pixmap scale if we have one (handled in next update)
        if hasattr(self, 'pixmap') and self.pixmap():
            # In real-time this is updated at 30fps anyway
            pass

    def mouseDoubleClickEvent(self, event):
        """Toggle full screen / popout view."""
        if self.isWindow():
            self.setWindowFlags(Qt.Widget)
            self.showNormal()
            if hasattr(self, 'parent_widget') and self.parent_widget:
                self.setParent(self.parent_widget)
                self.parent_layout.addWidget(self)
        else:
            self.parent_widget = self.parent()
            self.parent_layout = self.parent_widget.layout() if self.parent_widget else None
            self.setParent(None)
            self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
            self.setWindowTitle("LaserPAT - 3D Sideways View (Double Click to return)")
            self.showMaximized()


if __name__ == "__main__":
    import sys
    import math
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    
    app = QApplication(sys.argv)
    viewer = WorldView3DWidget(2000, 2000, display_size=(1024, 768))
    viewer.setWindowTitle("LaserPAT 3D Isometric View - Standalone Test")
    viewer.show()
    
    # Mock simulation variables
    frame = 0
    
    def update_mock_sim():
        global frame
        frame += 1
        
        # Circular beacon motion
        t = frame * 0.05
        beacon_x = 1000 + math.cos(t) * 400
        beacon_y = 1000 + math.sin(t) * 400
        
        # Gimbal tracking slightly behind
        gimbal_x = beacon_x - math.cos(t) * 20
        gimbal_y = beacon_y - math.sin(t) * 20
        
        # Platform moving linearly
        platform_x = 1000 + (frame % 400) - 200
        platform_y = 500
        
        # Distractors
        distractors = [
            (600, 800, 8, 8),
            (1400, 1200, 12, 12)
        ]
        
        # Simulate tracking states
        state = "LOCKED" if (frame % 200) < 150 else "SEARCH"
        
        viewer.update_world_3d(
            beacon_x=beacon_x, beacon_y=beacon_y,
            gimbal_x=gimbal_x, gimbal_y=gimbal_y,
            fov_px=(640, 480),
            platform_x=platform_x, platform_y=platform_y,
            tracking_state=state,
            distractors=distractors
        )
        
    timer = QTimer()
    timer.timeout.connect(update_mock_sim)
    timer.start(33) # ~30 FPS
    
    sys.exit(app.exec())
