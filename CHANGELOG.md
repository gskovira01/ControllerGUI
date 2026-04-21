# Changelog

All notable changes to the ControllerGUI / TIM Motion Service are documented here.

---

## [Unreleased] — 2026-04-21 (session 2)

### TIM Service — `tim_motion_server.py`
- **Fix: TCP receive buffer discard bug** — `_recv_line` was discarding all data after the first `\n` in a batched TCP packet (Nagle coalescing). Commands 2+ in a batch were silently dropped, leaving the GUI waiting for responses that never came. Replaced with a persistent per-client `recv_buf` that retains leftover data across reads.

### TIM Service — `tim_rapidcode_adapter.py`
- **Feature: Axis direction reversal** — Added `reverse: true` config flag per axis. When set, the adapter applies `motor_target = max_pos − user_setpoint` on outgoing commands and `user_pos = max_pos × scale − raw_pos` on incoming readbacks. Relative moves have their sign negated. No drive or hardware changes needed. See `tim_service/README.md` for full details.
- **Fix: Zero Position persistence** — Position offsets (set via the Zero Position button) are now saved to `tim_position_offsets.json` and restored after every service restart. Previously the offset was lost on restart and the user had to re-zero each session.

### GUI — `ControllerGUI.py`
- **Fix: Genuine zero actuals suppressed as N/A** — When a reversed axis parks at 0° (its natural end-of-travel), the GUI's zero-suppression logic previously rejected the reading as spurious after seeing prior non-zero values, eventually showing N/A. Fixed by accepting 0° as genuine after 3 consecutive zero readings (uses the existing `_consecutive_zero_actuals` counter that was tracked but not wired into the validity check).

---

## [2026-04-21] — commits `b68f184`, `c3fe668`

### GUI — `ControllerGUI.py`
- **Feature: Reconnect button** — Added per-servo Reconnect button next to the Link indicator. Calls `_reconnect_rsi()` on the appropriate comm object without restarting the GUI. Result logged to debug window.
- **Feature: Comm errors in GUI log** — Custom `logging.Handler` posts `WARNING`/`ERROR` records from all modules (including `communications.py`) to the GUI debug log via `write_event_value`. No terminal needed to see comm errors.
- **Fix: Jogging for Axes A-D** — `PR` stages a move in RapidCode but `BG` is required to execute it. Jog now sends `SP`/`AC`/`DC`/`PR`/`BG` in sequence. Previously no motion occurred on jog for A-D.
- **Fix: Jog direction on reversed axes** — CW/CCW sign is flipped for axes with `reverse = true` in the INI so CW = toward backswing and CCW = toward finish.
- **Fix: Jog limit indicator not clearing** — Indicator now clears immediately when a jog succeeds in the opposite direction rather than waiting for the POSITION_POLL `elif` chain.
- **Fix: Jog blocked by stale startup actuals** — Pre-jog limit enforcement now requires `pos_is_fresh` (position updated within 1.5s). Dirty startup actuals no longer falsely block valid jogs.
- **Cleanup:** Removed `import time as _time` inside function body; use module-level `time` import.

### Config — `controller_config.ini`
- **Added `reverse = true` to `[AXIS_A]`** — Single source of truth for direction reversal, read by both GUI (`AXIS_UNITS`) and TIM service adapter.

### TIM Service — `tim_rapidcode_adapter.py`
- **Cleanup:** Removed stale `TODO: Implement EtherCAT slave discovery` comment — ENI file rebuild covers this at the hardware level.

---

## [2026-04-19] — commit `79ca3d3`

### TIM Service
- **Fix: Axis init race condition** — `AxisCountGet()` and axis object caching moved to `_post_network_start_axis_init()`, called after `NetworkStart()`. Previously these ran before the EtherCAT network was OPERATIONAL, returning 0 axes and skipping `UserUnitsSet`, software limits, and CSP mode for all axes.
- **Feature: E-STOP broadcast** — E-STOP now broadcasts to all connected clients, not just the originating connection.
- **Removed:** Reset Tuning button removed from GUI.

---

## [2026-04-18] — commit `d4fbb2b`

### TIM Service
- **Config: Tuned MyActuator drive parameters** — Verified and locked in calibration constants for Servo A and B:
  - `scaling = 364.0888` (17-bit absolute encoder, 131072 counts/rev ÷ 360°)
  - `gearbox = 1.0` (EtherCAT firmware reports output-shaft position; gearbox is invisible to RapidCode)

---

## [2026-04-17] — commits `6180a4a`, `85427d9`, `e09d1ec`

### TIM Service
- **Config: Jerk added** — Jerk set to 20% per axis in `tim_config.yaml` for S-curve motion smoothing.
- **Fix: Stale INI override on iPC400** — Axis config from `controller_config.ini` was overwriting yaml values on the iPC400 even when the yaml had been updated. Fixed load order so yaml values take precedence when present.
- **Fix: TCP connection drops (WinError 10054)** — Added `_recv_line()` helper to read until `\r\n`, preventing two commands from being batched as one dispatch. Added `_reconnect_rsi()` with one retry on fresh socket for OSError recovery.
- **Fix: Actuals always 0 (TCP buffer accumulation)** — TIM service sends a response for every command including action commands ("1"). Old GUI code only `recv`'d after query commands; action responses piled up and stale "1" responses were read as position data (~0°). Fixed: `send_command` in `communications.py` now always `recv`'s after every send, inside the lock.
- **Fix: Polling thread crash (NameError)** — `torque_cmd`, `status_cmd`, `speed_cmd`, and response variables were used before assignment at the top of the polling loop. All 8 variables now initialized at loop entry in `ControllerPolling.py`.
- **Fix: Drift to zero after motor stops** — EtherCAT/RapidCode briefly returns 0 during state transitions at end of move. GUI consecutive-zero counter was forcing display to '0' after 3 zeros regardless of context. Fixed: zeros now suppressed only if motor was previously at a non-zero position (`has_seen_nonzero` guard); genuine zero setpoint always accepted.
- **Fix: Axis E comm health** — ClearCore connection stability improvements; aligned TIM docs and config.

---

## [2026-04-11] — commits `a74831c` through `4e228e5`

### TIM Service (initial bring-up)
- Scaffolded full TIM Motion Service: TCP socket server (port 503), axis router, RapidCode adapter (A–D), ClearCore adapter (E), safety watchdog, YAML config, unit tests.
- Fixed RapidCode SDK import: try `RapidCodePython` (RSI 11.x) before `RSI.RapidCode`.
- Fixed `MotionController` creation to use `CreationParameters` + `MotionController.Create()` (hardware path) rather than `CreateFromSoftware()`.
- Added RSI 11.x and INtime runtime DLL paths inside the service process.
- Pinned NumPy below 2.0 for RSI RapidCode compatibility.
- Config path resolution fixed for launch outside `tim_service/` directory.
- Task Scheduler: AtLogon trigger, 30s delay, run as logged-in user (not SYSTEM).

---

## Notes

- **iPC400 service files:** `C:\TIM\ControllerGUI\tim_service\`
- **GUI runs from:** `d:\Python\ControllerGUI\ControllerGUI.py` on the engineering laptop (not copied to iPC400)
- **Files that must be copied to iPC400 after changes:** `tim_rapidcode_adapter.py`, `tim_motion_server.py`, `tim_config.yaml`, `tim_axis_router.py`, `tim_clearcore_adapter.py`, `tim_motion_service.py`
- **Files that do NOT need copying:** `ControllerGUI.py`, `communications.py`, `ControllerPolling.py` (GUI-side only)
