| PPT claim | Actual code | Gap |
|---|---|---|
| Triple-threaded: UI / Sim / Processing | Headless = 1 thread; GUI has SimWorker+ProcessingWorker QThreads | OK for headless; GUI matches |
| YOLOv8 primary, Classical fallback | Both exist as selectable backends, not primary/fallback | Config `backend:` switches; default is `classical_cnn` |
| Lock window (stable offset) | PID drives error → 0, no lock window | **MISSING** |
| 300 seeded runs, reproducible | `random.uniform` unseeded in runner | **MISSING** |
| Results from actual runs | No `results_summary.json` | **MISSING** |
| Acquisition ≤ 2s median 0.33s | Unverified — no benchmark run | **UNVERIFIED** |
