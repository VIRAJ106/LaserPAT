"""Quick test to verify RandomWalkMotion stays within bounds"""
import sys
sys.path.insert(0, '.')

from src.environment.motion import RandomWalkMotion

def test_random_walk_boundaries():
    """Test that random walk motion stays within world bounds"""
    print("Testing RandomWalkMotion boundary reflection...")
    
    # Create random walk starting near boundary to test reflection
    motion = RandomWalkMotion(start_pos=(150, 150), max_step=50.0, world_bounds=(2000, 2000))
    
    # Track min/max positions over many steps
    min_x, max_x = 2000, 0
    min_y, max_y = 2000, 0
    out_of_bounds_count = 0
    
    # Simulate 1000 steps
    for i in range(1000):
        x, y = motion.step(dt=1.0)
        
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
        
        # Check if beacon went out of safe zone [100, 1900]
        if x < 100 or x > 1900 or y < 100 or y > 1900:
            out_of_bounds_count += 1
            if out_of_bounds_count <= 5:  # Print first few violations
                print(f"  Step {i}: OUT OF BOUNDS at ({x:.1f}, {y:.1f})")
    
    print(f"\nResults after 1000 steps:")
    print(f"  X range: [{min_x:.1f}, {max_x:.1f}]")
    print(f"  Y range: [{min_y:.1f}, {max_y:.1f}]")
    print(f"  Out of bounds violations: {out_of_bounds_count}/1000")
    
    # Calculate percentage of time in bounds
    in_bounds_percent = ((1000 - out_of_bounds_count) / 1000) * 100
    print(f"  In-bounds percentage: {in_bounds_percent:.1f}%")
    
    # Pass criteria: >95% in bounds (allows for <5% loss as per spec)
    if in_bounds_percent >= 95.0:
        print("\n[PASS] Random walk stays within bounds (>95% retention)")
        return True
    else:
        print(f"\n[FAIL] Too much boundary escape ({100-in_bounds_percent:.1f}% loss)")
        return False

if __name__ == "__main__":
    passed = test_random_walk_boundaries()
    sys.exit(0 if passed else 1)
