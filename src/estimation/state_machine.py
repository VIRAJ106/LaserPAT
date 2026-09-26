from enum import Enum

class TrackingState(Enum):
    IDLE = 0
    SEARCH = 1
    ACQUIRE = 2
    LOCKED = 3
    COAST = 4
    LOST = 5
    REACQUIRE = 6

class StateMachine:
    """
    Manages the transitions of the Tracking State Machine based on error metrics and temporal persistence.
    """
    def __init__(self, lock_threshold_px: float = 10.0, required_lock_frames: int = 3,
                 max_coast_frames: int = 30, max_lost_frames: int = 180,
                 acquire_miss_tolerance: int = 5, lock_miss_tolerance: int = 3):
        self.state = TrackingState.IDLE
        self.lock_threshold = lock_threshold_px
        self.required_lock_frames = required_lock_frames
        self.max_coast_frames = max_coast_frames
        self.max_lost_frames = max_lost_frames
        # NEW: how many consecutive missed frames are tolerated before abandoning
        self.acquire_miss_tolerance = acquire_miss_tolerance  # in ACQUIRE/REACQUIRE
        self.lock_miss_tolerance = lock_miss_tolerance        # in LOCKED before COAST
        
        self.consecutive_valid_frames = 0
        self.coast_frames = 0
        self.lost_frames = 0
        self._acquire_miss_streak = 0  # NEW
        self._lock_miss_streak = 0     # NEW
        
    def reset(self):
        self.state = TrackingState.IDLE
        self.consecutive_valid_frames = 0
        self.coast_frames = 0
        self.lost_frames = 0
        self._acquire_miss_streak = 0
        self._lock_miss_streak = 0
        
    def start_search(self):
        self.state = TrackingState.SEARCH
        self.consecutive_valid_frames = 0
        self.coast_frames = 0
        self.lost_frames = 0
        self._acquire_miss_streak = 0
        self._lock_miss_streak = 0
        
    def update(self, valid_detection: bool, euclidean_error: float = float('inf')) -> TrackingState:
        if self.state == TrackingState.IDLE:
            return self.state
            
        if self.state == TrackingState.SEARCH:
            if valid_detection:
                self.state = TrackingState.ACQUIRE
                self.consecutive_valid_frames = 1
                self._acquire_miss_streak = 0
                
        elif self.state == TrackingState.ACQUIRE or self.state == TrackingState.REACQUIRE:
            if valid_detection:
                self._acquire_miss_streak = 0
                if euclidean_error <= self.lock_threshold:
                    self.consecutive_valid_frames += 1
                    if self.consecutive_valid_frames >= self.required_lock_frames:
                        self.state = TrackingState.LOCKED
                        self.coast_frames = 0
                        self._lock_miss_streak = 0
                else:
                    # Detection valid but not yet locked — keep trying, don't reset counter fully
                    self.consecutive_valid_frames = max(0, self.consecutive_valid_frames - 1)
            else:
                # Missed detection — tolerate a few misses before abandoning
                self._acquire_miss_streak += 1
                if self._acquire_miss_streak >= self.acquire_miss_tolerance:
                    self.state = TrackingState.SEARCH
                    self.consecutive_valid_frames = 0
                    self._acquire_miss_streak = 0
                
        elif self.state == TrackingState.LOCKED:
            if not valid_detection:
                # Require consecutive misses before entering COAST (hysteresis)
                self._lock_miss_streak += 1
                if self._lock_miss_streak >= self.lock_miss_tolerance:
                    self.state = TrackingState.COAST
                    self.coast_frames = 1
                    self.consecutive_valid_frames = 0
                    self._lock_miss_streak = 0
            else:
                self._lock_miss_streak = 0  # reset on any valid detection
                self.consecutive_valid_frames += 1
                
        elif self.state == TrackingState.COAST:
            if valid_detection:
                self.state = TrackingState.LOCKED
                self.coast_frames = 0
                self.consecutive_valid_frames = 1
            else:
                self.coast_frames += 1
                if self.coast_frames >= self.max_coast_frames:
                    self.state = TrackingState.LOST
                    
        elif self.state == TrackingState.LOST:
            if valid_detection:
                self.state = TrackingState.REACQUIRE
                self.consecutive_valid_frames = 1
                self.lost_frames = 0
            else:
                # NEW: Count frames in LOST state
                self.lost_frames += 1
                # After max_lost_frames, return to SEARCH (restart from center)
                if self.lost_frames >= self.max_lost_frames:
                    self.state = TrackingState.SEARCH
                    self.lost_frames = 0
                
        return self.state
