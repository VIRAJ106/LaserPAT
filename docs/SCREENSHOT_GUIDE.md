# LaserPAT Screenshot Guide
## Reference for User Guide Documentation

This document maps the actual LaserPAT UI screenshots to the User Guide figure references.

---

## 📸 Screenshot Inventory

### **Mission Operations Screens**

#### **Figure: Mission Operations - IDLE State**
**Filename**: `mission-operations-idle.png`
**Description**: Initial idle state before starting simulation
**Shows**:
- State indicator: IDLE (gray/white)
- Empty camera feed (black screen)
- Tracking Statistics panel (all values at ---)
- Start Simulation button (blue, enabled)
- Real-Time Error History (empty graph)

---

#### **Figure: Mission Operations - ACQUIRE State**
**Filename**: `mission-operations-acquire.png`
**Description**: System acquiring target after detection
**Shows**:
- State indicator: ACQUIRE (orange/yellow)
- Camera feed with green detection box around beacon
- Tracking Error: ~4.25 px (decreasing)
- Gimbal Position: (739.7, 1278.5)
- Target Position: (742.3, 1281.1)
- Error plot showing sharp drop from ~100px to near zero
- Stop Simulation button (red)

**Key Observations**:
- Green crosshair reticle visible in camera
- Error rapidly converging
- State transition in progress

---

#### **Figure: Mission Operations - LOCKED State**
**Filename**: `mission-operations-locked.png`
**Description**: Successful tracking lock achieved
**Shows**:
- State indicator: LOCKED (green)
- State button bar at top showing progression: IDLE → SEARCH → ACQUIRE → **LOCKED** (highlighted) → COAST → LOST → REACQUIRE
- Camera feed with beacon tracked at center
- Tracking Error: **0.74 px** (sub-pixel accuracy!)
- Gimbal Position: (0.0, 0.0) - centered
- Target Position: (0.0, 0.0) - centered
- Error plot showing stable line near zero (~1.5 px oscillation)
- Stop button visible

**Key Observations**:
- Perfect center tracking (both gimbal and target at origin)
- Sub-pixel tracking error achieved
- State progression bar shows LOCKED as active state
- Green UI theme indicating success

---

### **Configuration Screens**

#### **Figure: Configuration & Tuning**
**Filename**: `configuration-tuning.png`
**Description**: Advanced parameter configuration panel
**Shows**:

**Live Hardware Tuning Section**:
- **PID Controller**:
  - Kp: 0.15 (slider)
  - Ki: 0.01 (slider)
  - Kd: 0.01 (slider)
  
- **Image Noise (User Selectable)**:
  - Gaussian Sigma: 20.00 (slider)
  - ☑ Gaussian (enabled)
  - ☑ Poisson (enabled)
  - ☐ Salt_Pepper (disabled)
  - Jitter (px): 20.00 (slider, full range)

**Environment Simulation Section**:
- Atmospheric Weather: clear (dropdown)
- Target Motion Profile: Straight (dropdown)
- Platform Disturbance: Static (dropdown)

**Key Observations**:
- All controls are live-adjustable sliders
- Checkbox toggles for noise types
- Dropdown menus for preset configurations
- Dark theme with cyan/blue accents

---

#### **Figure: Configuration - Core Scenario Settings**
**Filename**: `configuration-core-settings.png`
**Description**: Extended configuration showing more options
**Shows**:

**Scene / World Section**:
- World Width (px): 2000
- World Height (px): 2000

**Target (Beacon) Section**:
- Shape: square (dropdown)
- Size Width (px): 20
- Size Height (px): 20
- Initial Location: random (dropdown)

**Multi-Beacon (Optional)** - "earns Innovation points":
- (Innovation feature indicator)

**Live Hardware Tuning**:
- Atmospheric Weather dropdown expanded showing options:
  - clear
  - haze
  - fog
  - rain
  - low_light

**Key Observations**:
- Spinbox controls for numeric values
- Innovation feature callout for multi-beacon
- Weather dropdown expanded showing all options

---

### **Performance & Analytics Screens**

#### **Figure: 10-Scenario Benchmark Results**
**Filename**: `10-scenario-benchmark-results.png`
**Description**: Comprehensive performance validation table
**Shows**:

**Table Header**: "10-SCENARIO BENCHMARK RESULTS"

| Scenario | RMS Error | Max Error | Lock % | Verdict |
|----------|-----------|-----------|--------|---------|
| Slow Linear / Zero Noise | **3.1 px** (cyan) | 8.4 px | **99.2%** (green) | **PASS** (green badge) |
| Moderate Random / Low Noise | **3.9 px** (cyan) | 12.2 px | **96.1%** (green) | **PASS** (green badge) |
| Fast Angular Rate (LEO) | **5.4 px** (cyan) | 15.1 px | **94.5%** (green) | **PASS** (green badge) |
| Light Turbulence (Cn2=1e-15) | **4.8 px** (cyan) | 14.3 px | **95.0%** (green) | **PASS** (green badge) |
| Heavy Turbulence (Cn2=1e-13) | **8.9 px** (cyan) | 21.0 px | **89.2%** (orange) | **PASS** (green badge) |
| Platform Vibration (10Hz) | **6.2 px** (cyan) | 18.5 px | **92.4%** (green) | **PASS** (green badge) |
| Platform Vibration (50Hz) | **11.5 px** (cyan) | 25.2 px | **84.1%** (orange) | **BOUNDARY** (orange badge) |
| Heavy Fog / Attenuation | **9.4 px** (cyan) | 22.1 px | **86.8%** (orange) | **BOUNDARY** (orange badge) |
| Turbulence + Vibration | **14.2 px** (cyan) | 29.4 px | **79.5%** (red) | **BOUNDARY** (orange badge) |
| All Disturbances (σ=50) | **16.7 px** (cyan) | 38.1 px | **74.3%** (red) | **FAIL** (red badge) |

**Key Observations**:
- Color-coded RMS values (cyan = readable)
- Lock % color changes: green (>90%), orange (80-90%), red (<80%)
- Verdict badges: green (PASS), orange (BOUNDARY), red (FAIL)
- Gradient from easy (3.1px) to extreme (16.7px)
- Professional dark theme with excellent contrast

---

#### **Figure: A/B Live Comparison (Classical vs AI Enhanced)**
**Filename**: `ab-live-comparison.png`
**Description**: Real-time ablation study demonstrating AI improvement
**Shows**:

**Header**: "A/B Live Comparison (Classical vs AI Verifier)"

**Description Text**: 
"Auto-runs two headless 30-second simulations side-by-side using the SIH Benchmark weather conditions, highlighting the lock rate and RMSE improvements when the AI Verifier is enabled."

**Green Button**: "▶ RUN LIVE 30S COMPARISON"

**Comparison Results** (Terminal-style output):

```
A/B Comparison: Classical Filter VS AI-Enhanced (CNN)

Metric             Classical Filter  AI-Enhanced (CNN)  Δ
Lock Rate (%)      99.8              99.8               +0.0
Mean Error (px)    0.64              0.57               -0.07
RMSE (px)          0.66              0.59               -0.05
Max Error (px)     1.23              1.19               -0.03
```

**Key Observations**:
- Side-by-side comparison format
- Delta (Δ) column showing improvements
- AI shows consistent small improvements (~0.05-0.07 px)
- Both achieve 99.8% lock rate
- Terminal/console aesthetic for technical credibility

---

## 🎨 UI Design Observations

### **Color Scheme**:
- Background: Dark navy/black (#0a0f1a, #1a1f2e)
- Primary Accent: Cyan (#38bdf8, #22d3ee) - used for values, highlights
- Success: Green (#10b981, #22c55e) - PASS badges, LOCKED state
- Warning: Orange (#f59e0b, #fb923c) - BOUNDARY badges, moderate lock %
- Error: Red (#ef4444, #dc2626) - FAIL badges, low lock %
- Text Primary: White/off-white (#f8fafc, #e2e8f0)
- Text Secondary: Gray (#94a3b8, #64748b)

### **Typography**:
- Headers: Orbitron (bold, all-caps, glowing cyan)
- Monospace Values: Share Tech Mono (for metrics, coordinates)
- Body Text: Inter/system sans-serif

### **Layout Patterns**:
- Left sidebar navigation (Operations, Telemetry, Analytics, Configuration, A/B Benchmark)
- Main content area with header
- Right statistics panel (Tracking Statistics, Simulation Controls)
- Horizontal state indicator bar at top
- Consistent padding/spacing (~16-20px)

### **Interactive Elements**:
- Sliders: Blue track, white knob
- Buttons: Rounded rectangles with colored backgrounds
- Dropdowns: Dark background, subtle border
- Checkboxes: Filled when active (blue)
- State buttons: Highlighted when active (orange/green/red)

---

## 📝 Mapping to User Guide Figures

### **Quick Start Section**:
- Figure 1-4: External (GitHub, Windows dialogs)
- Figure 6: Use `mission-operations-idle.png` (splash screen equivalent)

### **Interface Overview Section**:
- Figure 7: Create composite labeled diagram from `mission-operations-locked.png`
- Figure 8: Use `mission-operations-locked.png` camera feed closeup
- Figure 9: (Need 2D world view screenshot)
- Figure 10: (Need 3D world view screenshot)
- Figure 11: Use error plot from `mission-operations-locked.png`
- Figure 12: Use `configuration-tuning.png`
- Figure 13: Create state indicator close-up from any mission-operations image
- Figure 14: Use statistics panel from `mission-operations-locked.png`

### **Running First Simulation**:
- Figure 15-17: Use `configuration-core-settings.png`
- Figure 18: Create animation from IDLE → ACQUIRE → LOCKED sequence
- Figure 19: Use `mission-operations-locked.png` statistics
- Figure 20: Use `mission-operations-locked.png` camera view
- Figure 21: (Need 2D world view during tracking)
- Figure 22: Use `mission-operations-locked.png` error plot
- Figure 23: Use final statistics panel

### **Performance Analysis**:
- Figure 54: Use `10-scenario-benchmark-results.png`
- Figure 58: Use `ab-live-comparison.png`

---

## 🔄 Missing Screenshots Needed

To complete the User Guide, you still need:

### **High Priority**:
1. **2D Top-Down World View** (during tracking)
   - Should show blue FOV rectangle, yellow beacon, green trail
   - Grid with coordinates
   - Velocity arrows

2. **3D Sideways World View**
   - Camera mast, frustum cone, beacon sphere
   - Gradient sky/ground, beacon trail
   - Isometric perspective

3. **Multi-Beacon Mode**
   - Camera view showing primary (cyan) + distractors (orange)
   - World view with labeled beacons

4. **Error Plot Close-up**
   - Different tracking patterns (clean, acquisition, oscillation)

5. **Different Motion Patterns**
   - Circular trajectory in world view
   - Random walk with boundary reflections

### **Medium Priority**:
6. Windows installation dialogs
7. GitHub download page
8. PyQtGraph 3D rendering
9. CSV log file in Excel
10. Parameter panel fully expanded

### **Low Priority (Can be illustrated)**:
11. Troubleshooting scenarios
12. State transition animations
13. Scenario preset loading
14. Performance summary reports

---

## 📸 Screenshot Capture Instructions

### **Recommended Tools**:
- **Windows Game Bar**: Win + G → Capture → Screenshot (Win + Alt + PrtScn)
- **Snipping Tool**: Win + Shift + S (rectangular snip)
- **ShareX**: Advanced with annotations
- **OBS Studio**: For video → frame extraction

### **Capture Guidelines**:

1. **Resolution**: 1920×1080 (Full HD)
2. **Format**: PNG (lossless)
3. **Naming**: Descriptive, lowercase, hyphens
   - Example: `mission-operations-locked.png`
   - Example: `configuration-pid-tuning.png`

4. **Composition**:
   - Center the relevant UI element
   - Include enough context (sidebars, headers)
   - Avoid partial windows or cropped text
   - Ensure high contrast (avoid washed-out colors)

5. **Consistency**:
   - Same window size (1200×800 or 1400×900 app window)
   - Same theme (dark mode enabled)
   - Same font rendering (ClearType enabled)

6. **Post-Processing**:
   - Crop to relevant area (remove desktop clutter)
   - Add annotations (arrows, boxes, labels) if needed
   - Compress PNGs (use TinyPNG or similar)
   - Target <500KB per image

---

## 🎨 Annotation Standards (For Labeled Figures)

When creating annotated diagrams (e.g., Figure 7: Main Interface Labeled):

### **Arrow Style**:
- Color: Bright cyan (#38bdf8) or yellow (#fbbf24)
- Width: 3-4px
- Style: Solid line with arrowhead

### **Label Boxes**:
- Background: Semi-transparent dark (#1e293bcc)
- Border: 1px solid cyan (#38bdf8)
- Text: White, 12-14pt, sans-serif
- Padding: 8px

### **Numbering**:
- Use circled numbers: ①②③④⑤⑥
- Color: Match annotation color
- Size: 18-20pt

### **Example Tools**:
- **Figma**: Best for complex annotations
- **Photoshop/GIMP**: Full control
- **Snagit**: Quick annotations
- **draw.io**: Vector diagrams

---

## 🚀 Quick Wins

**Most Important Screenshots for User Guide**:

✅ **Already Have**:
1. Mission Operations - IDLE ✓
2. Mission Operations - ACQUIRE ✓
3. Mission Operations - LOCKED ✓
4. Configuration & Tuning ✓
5. 10-Scenario Benchmark Results ✓
6. A/B Comparison ✓

🎯 **Need Next** (Top 5):
1. 2D World View (during tracking)
2. 3D Sideways View
3. Multi-Beacon Camera View
4. Multi-Beacon World View
5. Different Error Plot Patterns

With these 11 screenshots, you can cover ~70% of the User Guide figures!

---

## 📦 Delivery Checklist

When providing screenshots for documentation:

- [ ] All images saved to `docs/user-guide/images/`
- [ ] Filenames match references in USER_GUIDE.md
- [ ] PNG format, <500KB each
- [ ] 1920×1080 source resolution minimum
- [ ] Consistent UI state (same theme, same window size)
- [ ] No personal information visible
- [ ] High contrast, readable text
- [ ] Annotated versions created where needed
- [ ] Copyright/watermark free
- [ ] Organized in subdirectories if many images:
  ```
  images/
    ├── interface/
    ├── configuration/
    ├── performance/
    ├── demos/
    └── troubleshooting/
  ```

---

## 🎓 Example Caption Format

For each figure in the User Guide:

```markdown
![Mission Operations - LOCKED State](images/mission-operations-locked.png)
*Figure 20: Camera view during locked tracking showing sub-pixel accuracy (0.74px RMS error)*
```

**Components**:
1. Alt text: Descriptive for accessibility
2. Path: Relative to USER_GUIDE.md
3. Caption: *Italic text explaining what to observe*

---

**Status**: 6 screenshots captured ✓ | 5 high-priority screenshots needed 🎯 | ~40+ figures remaining

Would you like me to:
1. Update the User Guide with the actual screenshots you've provided?
2. Create a photo session script for capturing the missing screenshots?
3. Generate mock screenshots for the missing images?
