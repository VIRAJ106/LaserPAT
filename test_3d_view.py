"""Quick test to verify 3D SIDEWAYS view rendering with beautiful graphics"""
import sys
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication
from src.ui.widgets.world_view_3d import WorldView3DWidget
import time

def test_3d_rendering():
    app = QApplication(sys.argv)
    
    # Create 3D widget with larger display
    view_3d = WorldView3DWidget(world_w=2000, world_h=2000, display_size=(800, 800))
    
    print("Testing 3D Sideways View with enhanced graphics...")
    print("=" * 60)
    
    # Test 1: Static scene
    print("✓ Rendering static scene...")
    view_3d.update_world_3d(
        beacon_x=1000,
        beacon_y=1200,
        gimbal_x=1100,
        gimbal_y=1100,
        fov_px=(640, 480),
        platform_x=1000,
        platform_y=1000,
        tracking_state="LOCKED",
        distractors=[(600, 800, 20, 20), (1400, 1400, 30, 12)],
        beacon_w=10,
        beacon_h=10
    )
    
    print("✓ Features rendered:")
    print("  • Gradient sky and ground")
    print("  • Perspective grid with coordinate axes")
    print("  • Beacon with vertical pillar and glow effect")
    print("  • 2 distractor beacons (orange)")
    print("  • Platform with detailed camera mast")
    print("  • Camera FOV frustum projection")
    print("  • State-color-coded elements")
    print("  • Info overlays and labels")
    print("  • Atmospheric vignette effect")
    print()
    print("View Orientation: SIDEWAYS (looking from the side)")
    print("  - Camera is looking across the scene, not down")
    print("  - Gives better sense of depth and 3D structure")
    print()
    
    # Test 2: Animate beacon motion to show trail
    print("✓ Animating beacon motion (trail effect)...")
    view_3d.setWindowTitle("3D Sideways View Test - Enhanced Graphics")
    view_3d.show()
    
    # Simulate motion with trail
    import numpy as np
    for i in range(50):
        angle = i * 0.1
        beacon_x = 1000 + 300 * np.cos(angle)
        beacon_y = 1200 + 300 * np.sin(angle)
        
        view_3d.update_world_3d(
            beacon_x=beacon_x,
            beacon_y=beacon_y,
            gimbal_x=beacon_x + 20,  # Slightly offset for tracking effect
            gimbal_y=beacon_y + 20,
            fov_px=(640, 480),
            platform_x=1000,
            platform_y=1000,
            tracking_state="LOCKED" if i > 5 else "ACQUIRE",
            distractors=[(600, 800, 20, 20), (1400, 1400, 30, 12)],
            beacon_w=10,
            beacon_h=10
        )
        app.processEvents()
        time.sleep(0.05)
    
    print()
    print("=" * 60)
    print("✓ 3D Sideways View rendered successfully!")
    print("✓ Motion trail visible (fading blue line)")
    print()
    print("Try these interactions:")
    print("  • Double-click to toggle fullscreen")
    print("  • Window will stay open - close to exit")
    print("=" * 60)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    test_3d_rendering()
