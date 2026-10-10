Thread model (headless/scenario_runner):
  Single thread — scenario_runner.py is a blocking loop at 30 fps
  (No QThread — PySide6 threads only used by main.py GUI mode)

Data flow per frame:
  beacon.step(dt)  →  platform.step(dt)
  disturb_model.step(platform)  →  DisturbanceState
  camera.capture_frame()  →  raw uint8 frame
  disturb_model.apply_to_frame()  →  disturbed frame
  perception.run(frame)  →  PerceptionResult
  cand_manager.update()  →  TargetIdentity | None
  supervisor.step(identity, gx, gy)  →  PATCommand
  servo.step(dt)  →  gimbal moves
  evaluate_handoff()  →  HandoffQualification
  logger.log_frame()

Module map:
  src/interfaces.py          — canonical contracts (no deps)
  src/config.py              — AppConfig + load_config
  src/environment/           — World, Beacon, Platform, Motion
  src/camera/                — Viewport, Gimbal, Sensor, SyntheticCameraSource
  src/disturbances/          — DisturbanceModel (unified), noise.py, weather.py
  src/detection/             — perception.py (factory), classical.py, neural.py,
                               ai_verifier.py, candidate_manager.py
  src/estimation/            — pat_supervisor.py, kalman.py, state_machine.py, handoff.py
  src/control/               — pid.py, servo_loop.py, search_patterns.py
  src/physics/               — turbulence.py, link_budget.py, attenuation.py
  src/logging/               — csv_logger.py, report.py
  src/modes/                 — scenario_runner.py, video_runner.py
  src/ui/                    — main_window.py, threads.py (GUI only)
