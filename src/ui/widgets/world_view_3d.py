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
        
        # Slightly smaller internal resolution for better performance (640x480)
        # while keeping the visual crisp via PySide scaling
        self.render_w = 800
        self.render_h = 600
        self.display_size = (self.render_w, self.render_h)
        
        self.setMinimumSize(400, 400)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #0f172a; border-radius: 8px; border: 1px solid #1e293b;")
        
        # Performance optimization: allow GPU scaling
        self.setScaledContents(False)  # We will scale manually but with fast transformation
        
        # 3D projection parameters - SIDEWAYS VIEW
        self.camera_distance = 3500
        self.camera_height = 600
        
        self.pitch = np.radians(20)
        self.yaw = np.radians(65)
        
        self.scale = 0.16
        self.offset_x = self.render_w / 2
        self.offset_y = self.render_h / 2 + 100
        
        self.beacon_trail = []
        self.max_trail_length = 50
        
        # CACHE the background to save massive CPU cycles
        self._bg_cache = None
        
        self._render_blank()

    def _init_bg_cache(self):
        """Pre-renders the static background and grid."""
        canvas = np.zeros((self.render_h, self.render_w, 3), dtype=np.uint8)
        
        # Gradient background (deep slate to slightly lighter horizon)
        for y in range(self.render_h):
            intensity = max(0, int(20 - abs(y - self.render_h * 0.4) * 0.05))
            canvas[y, :] = (42 + intensity, 23 + intensity, 15 + intensity)
            
        # Add a subtle vignette in the cache (done once!)
        X, Y = np.meshgrid(np.arange(self.render_w), np.arange(self.render_h))
        center_x, center_y = self.render_w / 2, self.render_h / 2
        dist = np.sqrt((X - center_x)**2 + (Y - center_y)**2)
        max_dist = np.sqrt(center_x**2 + center_y**2)
        vignette = np.clip(1.0 - (dist / max_dist) * 0.2, 0.8, 1.0)
        canvas = (canvas * vignette[..., np.newaxis]).astype(np.uint8)

        # Draw Ground Plane with Grid
        grid_spacing = 400
        grid_color = (60, 45, 30)
        for x in range(0, self.world_w + 1, grid_spacing):
            pt1 = self.project_3d_to_2d(x, 0, 0)
            pt2 = self.project_3d_to_2d(x, self.world_h, 0)
            cv2.line(canvas, pt1, pt2, grid_color, 1, cv2.LINE_AA)
        
        for y in range(0, self.world_h + 1, grid_spacing):
            pt1 = self.project_3d_to_2d(0, y, 0)
            pt2 = self.project_3d_to_2d(self.world_w, y, 0)
            cv2.line(canvas, pt1, pt2, grid_color, 1, cv2.LINE_AA)
            
        # Draw coordinate axes
        origin = self.project_3d_to_2d(0, 0, 0)
        x_axis = self.project_3d_to_2d(800, 0, 0)
        y_axis = self.project_3d_to_2d(0, 800, 0)
        
        cv2.arrowedLine(canvas, origin, x_axis, (50, 50, 255), 2, tipLength=0.05)
        cv2.arrowedLine(canvas, origin, y_axis, (200, 200, 50), 2, tipLength=0.05)
        
        cv2.putText(canvas, "X", (x_axis[0] + 5, x_axis[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (50, 50, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, "Y", (y_axis[0] + 5, y_axis[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 50), 1, cv2.LINE_AA)
        
        self._bg_cache = canvas

    def project_3d_to_2d(self, x, y, z):
        cx = x - self.world_w / 2
        cy = y - self.world_h / 2
        cz = z
        
        x_yaw = cx * np.cos(self.yaw) + cy * np.sin(self.yaw)
        y_yaw = -cx * np.sin(self.yaw) + cy * np.cos(self.yaw)
        z_yaw = cz
        
        x_final = x_yaw
        y_final = y_yaw * np.cos(self.pitch) - z_yaw * np.sin(self.pitch)
        z_final = y_yaw * np.sin(self.pitch) + z_yaw * np.cos(self.pitch)
        
        perspective_factor = 1.0 + (y_final / 3000.0)
        
        px = int(x_final * self.scale / perspective_factor + self.offset_x)
        py = int(-z_final * self.scale / perspective_factor + self.offset_y)
        
        return (px, py)

    def _draw_3d_box(self, canvas, cx, cy, cz, width, depth, height, color):
        """Draw a beautiful 3D isometric box."""
        w2, d2, h2 = width/2, depth/2, height/2
        corners = [
            (cx-w2, cy-d2, cz-h2), (cx+w2, cy-d2, cz-h2),
            (cx+w2, cy+d2, cz-h2), (cx-w2, cy+d2, cz-h2),
            (cx-w2, cy-d2, cz+h2), (cx+w2, cy-d2, cz+h2),
            (cx+w2, cy+d2, cz+h2), (cx-w2, cy+d2, cz+h2)
        ]
        pts = [self.project_3d_to_2d(*c) for c in corners]
        
        # Faces
        top = np.array([pts[4], pts[5], pts[6], pts[7]], np.int32).reshape((-1,1,2))
        side1 = np.array([pts[0], pts[1], pts[5], pts[4]], np.int32).reshape((-1,1,2))
        side2 = np.array([pts[1], pts[2], pts[6], pts[5]], np.int32).reshape((-1,1,2))
        
        # Darker sides for 3D lighting effect
        c_top = color
        c_s1 = (max(0, color[0]-50), max(0, color[1]-50), max(0, color[2]-50))
        c_s2 = (max(0, color[0]-25), max(0, color[1]-25), max(0, color[2]-25))
        
        cv2.fillPoly(canvas, [side1], c_s1, cv2.LINE_AA)
        cv2.fillPoly(canvas, [side2], c_s2, cv2.LINE_AA)
        cv2.fillPoly(canvas, [top], c_top, cv2.LINE_AA)
        
        # Edges
        cv2.polylines(canvas, [side1], True, (0,0,0), 1, cv2.LINE_AA)
        cv2.polylines(canvas, [side2], True, (0,0,0), 1, cv2.LINE_AA)
        cv2.polylines(canvas, [top], True, (255,255,255), 1, cv2.LINE_AA)

    def update_world_3d(self, beacon_x, beacon_y, gimbal_x, gimbal_y, 
                        fov_px=(640, 480), platform_x=None, platform_y=None,
                        tracking_state="IDLE", distractors=None, beacon_w=10, beacon_h=10):
                        
        if self._bg_cache is None:
            self._init_bg_cache()
            
        # Start with cached background for blazing fast performance
        canvas = self._bg_cache.copy()
        
        # === 1. Draw Beacon Motion Trail ===
        self.beacon_trail.append((beacon_x, beacon_y))
        if len(self.beacon_trail) > self.max_trail_length:
            self.beacon_trail.pop(0)
            
        if len(self.beacon_trail) > 1:
            trail_points = [self.project_3d_to_2d(tx, ty, 5) for tx, ty in self.beacon_trail]
            for i in range(len(trail_points) - 1):
                alpha = (i + 1) / len(trail_points)
                thickness = max(1, int(alpha * 3))
                intensity = int(alpha * 200)
                cv2.line(canvas, trail_points[i], trail_points[i+1], (intensity, intensity, 255), thickness, cv2.LINE_AA)

        # === 2. Draw Distractors ===
        if distractors:
            for dx, dy, dw, dh in distractors:
                # Draw as small red/orange boxes
                self._draw_3d_box(canvas, dx, dy, 25, max(40, dw*2), max(40, dh*2), 50, (30, 80, 220))

        # === 3. Draw Target Beacon (Glowing Sci-Fi Diamond/Pyramid) ===
        target_color = (255, 200, 0) # Cyan/Blue glow in BGR (0, 200, 255)
        # Shadow
        shadow_pt = self.project_3d_to_2d(beacon_x, beacon_y, 0)
        cv2.ellipse(canvas, shadow_pt, (15, 8), 0, 0, 360, (20,20,20), -1, cv2.LINE_AA)
        # Draw target as a hovering 3D box for now, looks much better than flat circles
        hover_height = 80
        # Draw laser beam from ground to beacon
        ground_pt = self.project_3d_to_2d(beacon_x, beacon_y, 0)
        top_pt = self.project_3d_to_2d(beacon_x, beacon_y, hover_height)
        cv2.line(canvas, ground_pt, top_pt, (target_color[0]//2, target_color[1]//2, target_color[2]//2), 2, cv2.LINE_AA)
        
        self._draw_3d_box(canvas, beacon_x, beacon_y, hover_height, 60, 60, 60, target_color)
        
        # Target label
        label_pos = (top_pt[0] - 20, top_pt[1] - 40)
        cv2.putText(canvas, "TARGET", label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)

        # === 4. Draw Platform and Camera ===
        if platform_x is None: platform_x = self.world_w / 2
        if platform_y is None: platform_y = self.world_h / 2
        
        camera_height = 300
        
        # Platform Base (Large 3D Box)
        self._draw_3d_box(canvas, platform_x, platform_y, 20, 160, 160, 40, (120, 120, 120))
        
        # Mast
        plat_ground = self.project_3d_to_2d(platform_x, platform_y, 40)
        cam_pos = self.project_3d_to_2d(platform_x, platform_y, camera_height - 20)
        cv2.line(canvas, plat_ground, cam_pos, (80, 80, 80), 4, cv2.LINE_AA)
        
        # Camera Unit (Smaller 3D Box)
        self._draw_3d_box(canvas, platform_x, platform_y, camera_height, 60, 80, 40, (180, 180, 180))
        
        # Platform label
        plat_lbl = self.project_3d_to_2d(platform_x, platform_y, 0)
        cv2.putText(canvas, "PLATFORM", (plat_lbl[0] - 30, plat_lbl[1] + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 180, 80), 1, cv2.LINE_AA)

        # === 5. Draw FOV Frustum ===
        fw, fh = fov_px
        corners = [
            (gimbal_x - fw/2, gimbal_y - fh/2),
            (gimbal_x + fw/2, gimbal_y - fh/2),
            (gimbal_x + fw/2, gimbal_y + fh/2),
            (gimbal_x - fw/2, gimbal_y + fh/2)
        ]
        
        fov_color = self._get_state_color(tracking_state)
        cam_lens = self.project_3d_to_2d(platform_x, platform_y, camera_height)
        
        for cx, cy in corners:
            corner_pt = self.project_3d_to_2d(cx, cy, 0)
            cv2.line(canvas, cam_lens, corner_pt, (fov_color[0]//2, fov_color[1]//2, fov_color[2]//2), 1, cv2.LINE_AA)
            
        ground_corners = [self.project_3d_to_2d(cx, cy, 0) for cx, cy in corners]
        pts = np.array(ground_corners, np.int32).reshape((-1, 1, 2))
        
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [pts], fov_color, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.15, canvas, 0.85, 0, canvas)
        cv2.polylines(canvas, [pts], True, fov_color, 2, cv2.LINE_AA)

        # === 6. UI Overlays ===
        cv2.putText(canvas, "3D ISOMETRIC VIEW", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        
        state_text = f" {tracking_state} "
        text_size = cv2.getTextSize(state_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
        badge_x = self.render_w - text_size[0] - 25
        
        cv2.rectangle(canvas, (badge_x - 5, 10), (badge_x + text_size[0] + 5, 30), (30, 41, 59), -1)
        cv2.rectangle(canvas, (badge_x - 5, 10), (badge_x + text_size[0] + 5, 30), fov_color, 1, cv2.LINE_AA)
        cv2.putText(canvas, state_text, (badge_x, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, fov_color, 1, cv2.LINE_AA)
        
        distance = np.hypot(beacon_x - gimbal_x, beacon_y - gimbal_y)
        info_text = f"Target: ({int(beacon_x)}, {int(beacon_y)})  |  Distance: {int(distance)}px"
        cv2.putText(canvas, info_text, (15, self.render_h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (148, 163, 184), 1, cv2.LINE_AA)
        
        self._display_canvas(canvas)

    def _get_state_color(self, state):
        color_map = {
            "LOCKED":    (0, 255, 0),
            "ACQUIRE":   (0, 255, 255),
            "COAST":     (0, 200, 255),
            "SEARCH":    (0, 100, 255),
            "REACQUIRE": (200, 0, 255),
            "LOST":      (0, 0, 255),
            "IDLE":      (100, 100, 100)
        }
        return color_map.get(state, (100, 100, 100))

    def clear_trail(self):
        self.beacon_trail = []
        
    def _display_canvas(self, canvas):
        h, w, ch = canvas.shape
        bytes_per_line = ch * w
        qimg = QImage(canvas.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pix = QPixmap.fromImage(qimg)
        # Use FastTransformation instead of SmoothTransformation for maximum FPS
        scaled_pix = pix.scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.FastTransformation)
        self.setPixmap(scaled_pix)

    def _render_blank(self):
        canvas = np.zeros((self.render_h, self.render_w, 3), dtype=np.uint8)
        canvas[:] = (42, 23, 15)
        cv2.putText(canvas, "3D ISOMETRIC VIEW", (self.render_w//2 - 80, self.render_h//2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (148, 163, 184), 1, cv2.LINE_AA)
        cv2.putText(canvas, "Start Tracking (Platform Moving) to begin", (self.render_w//2 - 120, self.render_h//2 + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 116, 139), 1, cv2.LINE_AA)
        self._display_canvas(canvas)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def mouseDoubleClickEvent(self, event):
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
    
    frame = 0
    def update_mock_sim():
        global frame
        frame += 1
        t = frame * 0.05
        beacon_x = 1000 + math.cos(t) * 400
        beacon_y = 1000 + math.sin(t) * 400
        gimbal_x = beacon_x - math.cos(t) * 20
        gimbal_y = beacon_y - math.sin(t) * 20
        platform_x = 1000 + (frame % 400) - 200
        platform_y = 500
        state = "LOCKED" if (frame % 200) < 150 else "SEARCH"
        
        viewer.update_world_3d(beacon_x, beacon_y, gimbal_x, gimbal_y, (640, 480), platform_x, platform_y, state, [(600, 800, 8, 8)])
        
    timer = QTimer()
    timer.timeout.connect(update_mock_sim)
    timer.start(33)
    sys.exit(app.exec())
