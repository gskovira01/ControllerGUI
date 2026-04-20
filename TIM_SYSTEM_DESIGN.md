# TIM System Design & Architecture

## System Overview

**TIM** is a 5-axis motion control system designed for high-speed servo control of a multi-axis mechanical manipulator. The system separates operator control (GUI PC) from field motion control (iPC400 industrial PC), allowing for robust, deterministic motion execution without blocking on the operator input side.

**Target Architecture**: All hardware motion I/O is owned and managed by the iPC400. The operator GUI is a remote client that sends commands and receives telemetry only.

**Current Deployment (2026-04-17)**: Hybrid mode is active.
- Axes A-D are intended to run through iPC400 TIM Motion Service (TCP/503).
- Axis E is currently controlled directly by GUI-to-ClearCore UDP.

---

## Hardware Configuration

### Primary Motion Axes (A–D): EtherCAT via RSI RapidCode
| Axis | Motor | Descr iption | Function |
|------|-------|-------------|----------|
| A | MyActuator RMD-X10 (EtherCAT) | Primary Rotation X12 | Main joint rotation |
| B | MyActuator RMD-X10 (EtherCAT) | Secondary Rotation X8 | Intermediate joint |
| C | MyActuator RMD-X10 (EtherCAT) | Tertiary Rotation X8 | Wrist rotation 1 |
| D | MyActuator RMD-X10 (EtherCAT) | Tertiary Lift X12 | Lift/linear motion |

**Controller**: RSI RapidCode/RMP on iPC400  
**Protocol**: EtherCAT over industrial Ethernet  
**Deterministic**: Real-time motion execution @ ~1 kHz cycle  
**Owned by**: iPC400 only

---

### Auxiliary Axis (E): ClearCore with Teknic Servo
| Axis | Motor | Description | Function |
|------|-------|-------------|----------|
| E | Teknic Clearcore + SDSK-3221 servo | Address Angle | Steering/orientation |

**Controller**: Teknic ClearCore processor  
**Protocol**: UDP command/response interface to ClearCore board  
**Coordination**: Non-real-time; fires independent of A-D motion  
**Current owner**: GUI PC direct UDP (CommMode6 in ControllerGUI)
**Target owner**: iPC400 (all ClearCore I/O traffic originates from iPC400 only)

---

### Optional Legacy Axis (H): Reserved for CAN
| Axis | Motor | Description | Status |
|------|-------|-------------|--------|
| H | MyActuator RMD-X10 (CAN bridge) | Legacy motor control | **Disabled for TIM** |

**Note**: Axis H wiring and code remain in place for future evaluation but is not active in TIM. The CAN-to-Ethernet bridge path is available if needed later.

---

### Unused Axes (F–G)
**Status**: Not implemented for this project. GUI tabs remain available for future expansion.

---

## Network Topology

```
┌─────────────────────────────────┐
│   OPERATOR GUI PC               │
│   (d:\Python\ControllerGUI\)   │
│                                 │
│   - 8-axis touchscreen interface│
│   - Sends motion commands       │
│   - Displays axis status        │
│   - Non-real-time (500ms polls) │
└────────────┬────────────────────┘
             │
             │ TCP port 503
             │ Galil-like ASCII over TCP
             │
┌────────────▼────────────────────┐
│   iPC400 INDUSTRIAL PC (TIM-PC) │
│                                 │
│  ┌──────────────────────────┐   │
│  │ TIM Motion Service       │   │
│  │ (Python/Win service)     │   │
│  │                          │   │
│  │ - Axis Router (A-D, E)   │   │
│  │ - Command dispatcher     │   │
│  │ - Telemetry collector    │   │
│  │ - Fault manager          │   │
│  │ - Watchdog & safety      │   │
│  └────┬──────────┬──────────┘   │
│       │          │               │
│   ┌───▼───┐   ┌──▼────────┐     │
│   │ RSI   │   │ ClearCore │     │
│   │Rapid  │   │ Board UDP │     │
│   │Code   │   │           │     │
│   └───┬───┘   └──┬────────┘     │
│       │          │               │
└───────┼──────────┼───────────────┘
        │          │
        │ EtherCAT │ UDP(static)
        │ (real-   │ 192.168.1.171:8888
        │ time,    │
        │ 1kHz)    │
        │          │
    ┌───▼──────────▼─────────────┐
    │  FIELD HARDWARE             │
    │  Axes A-D (EtherCAT motors) │
    │  Axis E (ClearCore + servo) │
    └─────────────────────────────┘
```

### Network Assumptions
- **GUI PC ↔ iPC400**: 192.168.1.151, port 503 (TCP, low latency assumed but not required)
- **iPC400 ↔ ClearCore**: 192.168.1.171, port 8888 (UDP, static config)
- **iPC400 ↔ EtherCAT slaves**: Deterministic EtherCAT over industrial Ethernet

---

## Deployment & Startup

### iPC400 (TIM-PC) Setup
1. Windows 11 with real-time networking drivers (optional, for future RT kernel support).
2. RSI RapidCode 10.7.1+ installed at default location.
3. EtherCAT network interface configured and tested.
4. ClearCore board powered and accessible via UDP at 192.168.1.171:8888.
5. TIM Motion Service installed as Windows Service or auto-launch app.
6. All motion state is **owned and persisted** on iPC400 only.

### GUI PC Setup
1. Python 3.10+ with FreeSimpleGUI and other dependencies.
2. Network connectivity to iPC400 at 192.168.1.151:503.
3. No RapidCode, no EtherCAT drivers.
4. Current deployment includes direct GUI UDP control of Axis E (ClearCore).

### Startup Sequence
1. **iPC400 boots**: TIM Motion Service starts, initializes EtherCAT stack, discovers slaves, waits for client.
2. **Operator launches GUI**: Connects to iPC400 at 192.168.1.151:503 for A-D and uses direct UDP to ClearCore for E.
3. **GUI receives status**: Queries A-D via iPC400 service and E via ClearCore path.
4. **Operator sends commands**: A-D routed through iPC400 service; E sent directly by GUI.
5. **Service executes A-D motion**: Returns status/position updates for A-D.

---

## Command Interface (Current Model)

### Galil-Like ASCII Protocol (Compatibility Layer)

The GUI sends commands using Galil DMC-4180 compatible syntax.
- Current deployment: iPC400 service translates A-D to RapidCode, while Axis E uses direct ClearCore UDP from GUI.
- Target architecture: iPC400 service translates both A-D and E.

**Example Commands Sent by GUI:**
```
SH A          # Enable axis A (RapidCode)
MO B          # Disable axis B (RapidCode)
PA C=45       # Absolute move axis C to 45 degrees (RapidCode)
PR D=10       # Relative move axis D by 10 degrees (RapidCode)
SP E=100      # Set speed axis E to 100 DPS (ClearCore)
TP A          # Query target position (RapidCode)
MG _RPA       # Query actual position (RapidCode)
MG _MO A      # Query enable state (RapidCode)
```

**Response Format:**
- **Queries**: Single numeric value per line (e.g., `45.0`)
- **Status**: Numeric enable/disable state (e.g., `1` = enabled, `0` = disabled)
- **Errors**: Non-numeric response or timeout indicates issue

### Future Migration Path

When TIM motion is stable, we will replace the Galil layer with a cleaner TIM API:
```
ENABLE_AXIS <axis>
DISABLE_AXIS <axis>
MOVE_ABS <axis> <degrees>
MOVE_REL <axis> <degrees>
SET_SPEED <axis> <dps>
SET_ACCEL <axis> <dps²>
STOP_AXIS <axis>
GET_STATUS <axis>
GET_POSITION <axis>
GET_FAULTS <axis>
HOME_AXIS <axis>
```

This change will be transparent to operators once finalized.

---

## Axis Mapping in Code

### Encoder & Scaling Reference (Axes A–D)

**Motor**: MyActuator RMD-X12 / RMD-X8, P20 variant (20:1 planetary gearbox), EtherCAT interface

| Parameter | Value | Notes |
|-----------|-------|-------|
| Encoder resolution | 17-bit (131,072 counts/rev) | Absolute encoder on motor shaft |
| Gearbox ratio | 20:1 | Handled **internally** by EtherCAT firmware |
| RapidCode view | 131,072 counts/output rev | Firmware reports output-shaft position |
| `scaling` constant | **364.0888** counts/degree | 131072 ÷ 360 |
| `gearbox` in config | **1** | Do NOT set to 20 — firmware already applies it |
| UserUnitsSet value | 364.0888 | Set at service init; `ActualPositionGet()` returns **degrees** |

**Key identity**: `scaling × gearbox = 364.0888 × 1.0 = 364.0888 counts/degree`

Verification: commanding 360° in RapidSetup produces exactly one output shaft revolution.

### Current Configuration (controller_config.ini)

`controller_config.ini` is the **single source of truth** for axis parameters — read by both the GUI and the TIM service at startup. Do not duplicate axis values in `tim_config.yaml`.

```ini
[CommMode1]
ip_address = 192.168.1.151   # iPC400 TIM Motion Service
port = 503
protocol = TCP

[CommMode6]
ip_address = 192.168.1.171   # ClearCore board (Axis E)
port = 8888
protocol = UDP

# Axes A–D: identical scaling constants
[AXIS_A]  # Primary Rotation
scaling = 364.0888    # 131072 counts/rev ÷ 360 degrees
gearbox = 1           # EtherCAT firmware hides the 20:1 gearbox
min = 0  /  max = 180

[AXIS_B]  # Secondary Rotation   (same scaling/gearbox as A)
[AXIS_C]  # Tertiary Rotation    (same scaling/gearbox as A)
[AXIS_D]  # Quaternary           (same scaling/gearbox as A)

[AXIS_E]  # Address Angle — Teknic ClearCore servo
scaling = 1870   gearbox = 1   min = 0   max = 45
```

---

## Axis Routing in GUI

[ControllerGUI.py](ControllerGUI.py) uses three comm channels:
- `comm` (CommMode1): iPC400 motion service for A-D
- `comm_e` (CommMode6): ClearCore board UDP (direct from GUI in current deployment)
- `comm_h` (CommMode5): MyActuator CAN (disabled for TIM)

**Future Simplification**: When iPC400 service owns ClearCore traffic, the GUI will consolidate to one TCP connection (CommMode1 only), and internal routing happens on the iPC400 side.

---

## Safety & Control Ownership

### On iPC400 (TIM-PC)
- **Current authority**: TIM Motion Service is authority for A-D.
- **Target authority**: TIM Motion Service will be sole authority for A-E.
- **Limit enforcement**: All software limits, enable interlocks, homing state (A-D currently through service).
- **Fault handling**: Axis faults are cleared only by authorized service commands.
- **Watchdog**: If GUI client disconnects, motion stops or enters safe state.
- **Enable logic**: Servo enable/disable controlled by service logic, not GUI state.

### On GUI PC
- **Operator intent only**: Send commands, receive feedback.
- **No real-time guarantees**: 500 ms polling cycle is informational, not control loop.
- **Current exception**: Axis E commands are sent directly to ClearCore via UDP.
- **Target mode**: No direct hardware once E is migrated behind iPC400 service.
- **Best-effort reliability**: Network loss is handled by iPC400 watchdog, not GUI retry logic.

---

## Polling & Telemetry

The GUI polls the iPC400 service at **2 Hz (500 ms cycle)** to update:
- Actual position (degrees and pulses)
- Enable/disable status
- Current velocity
- Fault flags (if any)

Each poll sends a Galil-style query command and waits for a numeric response.
- Current deployment: A-D telemetry is via iPC400 service; E telemetry is via direct ClearCore path.
- Target architecture: iPC400 service returns unified A-E telemetry.

---

## Development Environment

### GUI PC Development (Operator Interface)
**Your Primary Development Machine** (Laptop / Windows PC)

- **IDE**: VS Code with Python extension
- **Location**: `d:\Python\ControllerGUI\`
- **Venv**: `venv_rmp311` (or create GUI-specific venv)
- **Workflow**: Edit python files, test locally with mock/phantom hardware, commit to GitHub
- **Testing**: Can start TIM Motion Service mockup locally for integration testing

### iPC400 Development (TIM Motion Service)

**Recommended Setup: VS Code Native on iPC400**

- **IDE**: VS Code installed directly on iPC400 (recommended)
- **Location**: `C:\TIM\` or `C:\tim-motion-service\`
- **Venv**: Dedicated Python venv on iPC400 for TIM service
- **Workflow**: 
  - Develop code directly on iPC400 using VS Code (native speed, full hardware access)
  - Test against real RapidCode SDK when hardware is available
  - RDP or direct console for service deployment/debugging
  - Git operations via CMD/PowerShell on iPC400
- **Size**: VS Code is ~500MB; iPC400 has plenty of space

**Why Native VS Code on iPC400 vs RDP?**
- **RDP**: Can feel sluggish over network, screen lag during coding
- **Native VS Code**: Full speed, instant feedback, direct RapidCode debugging
- **Best practice**: Install VS Code on iPC400 once, develop there directly

**Optional: VS Code Remote SSH (Phase 3+)**
- When iPC400 migrates to Linux for real-time kernel (Phase 3), you can use VS Code Remote SSH development
- Allows developing on your laptop with iPC400 as the backend
- Requires SSH server on iPC400 (native in Linux, optional in Windows)
- Not needed for initial Windows-based development

### Repository Structure

```
GitHub (ControllerGUI repo):
├── gui_pc/                          # GUI side (your laptop)
│   ├── ControllerGUI.py
│   ├── communications.py
│   ├── ControllerPolling.py
│   ├── numeric_keypad.py
│   ├── controller_config.ini
│   ├── README.md
│   └── venv_rmp311/
│
├── tim_service/                     # iPC400 motion service (separate venv)
│   ├── tim_motion_service.py        # Main service entry point
│   ├── tim_motion_server.py         # TCP listener (port 503)
│   ├── tim_rapidcode_adapter.py     # RapidCode A-D wrapper
│   ├── tim_clearcore_adapter.py     # ClearCore E dispatcher
│   ├── tim_axis_router.py           # Command router by axis
│   ├── tim_config.yaml              # Service configuration
│   ├── tim_safety_watchdog.py       # Fault & watchdog manager
│   ├── tests/
│   │   ├── test_mock_rapidcode.py   # Mock RapidCode for testing
│   │   ├── test_axis_router.py
│   │   └── test_galil_translator.py
│   ├── requirements.txt             # TIM service dependencies
│   └── venv/                        # iPC400 local venv
│
├── TIM_SYSTEM_DESIGN.md             # This document
├── .gitignore
└── README.md
```

### Development Workflow

**Phase 1: GUI & Service Development (Parallel)**

| Task | Location | Tool |
|------|----------|------|
| Edit GUI code | GUI PC | VS Code |
| Test GUI locally | GUI PC | Python + mock service |
| Edit TIM service | iPC400 | VS Code (native) |
| Test service with mock RapidCode | iPC400 | Python + phantom axes |
| Integration test (GUI ↔ service) | Network | Both machines |
| Version control | Both machines | Git CLI |

**Phase 2: Hardware Integration Testing**

- RDP into iPC400 for service monitoring/debugging if needed
- Or work directly at iPC400 console with hardware
- GUI PC connects to iPC400 over network (192.168.1.151:503) for motion tests

**Phase 3: Production Deployment**

- iPC400 runs TIM service as Windows Service (auto-start)
- Updates via Git pull + service restart
- Monitoring via logs or optional SSH (if migrated to Linux)

### Python Environment Checklist

**GUI PC (d:\Python\ControllerGUI)**
- [ ] Python 3.10+
- [ ] FreeSimpleGUI
- [ ] NumPy 1.22.0
- [ ] PySerial (if needed)
- [ ] requests (for socket communication)

**iPC400 (C:\TIM)**
- [ ] Python 3.10+
- [ ] RSI RapidCode SDK 10.7.1+ installed at C:\RSI\10.7.1
- [ ] NumPy (RapidCode requirement)
- [ ] PyYAML (for config files)
- [ ] requests (for HTTP helpers)
- [ ] pytest (for unit tests)
- [ ] VS Code with Python extension (optional but recommended)

---

## File Structure & Modules

```
TIM-PC (iPC400):
  tim_motion_service.py        # Main service / entry point
  tim_motion_server.py         # TCP socket listener (port 503)
  tim_rapidcode_adapter.py     # RapidCode wrapper (A-D)
  tim_clearcore_adapter.py     # ClearCore dispatcher (E)
  tim_axis_router.py           # Route commands by axis
  tim_safety_watchdog.py       # Fault & watchdog manager
  config.ini or tim_config.yaml # Service configuration

GUI PC (d:\Python\ControllerGUI):
  ControllerGUI.py             # Main GUI (unchanged for now)
  communications.py            # Comm module (CommMode1 → iPC400)
  ControllerPolling.py         # 2 Hz polling thread
  controller_config.ini        # Axis / motor definitions
  numeric_keypad.py            # GUI input widget
  README.md                    # GUI documentation
  TIM_SYSTEM_DESIGN.md         # This document
```

---

## 10,000 ft Software Inventory (Active Runtime)

This section maps the active first-party software used in the current deployment. It intentionally excludes virtual environments, wheel caches, and historical archive backups.

### Engineering Workstation (Laptop)

| File | What It Does | Key Routines |
|------|--------------|--------------|
| `ControllerGUI.py` | Main operator GUI for servo tabs, setpoint entry, motion commands, fault controls, and on-screen telemetry. | `handle_servo_event`, `handle_all_run_sequence`, `apply_startup_motion_defaults`, `reset_motion_defaults`, `prepare_pvt_payload`, `send_pvt_payload`, `prepare_datapipe_segments`, `send_datapipe_contour` |
| `ControllerPolling.py` | Background polling and communications health monitoring for UI updates. | `polling_thread_func`, `start_polling_thread`, `comm_health_thread_func`, `start_comm_health_thread` |
| `communications.py` | Unified transport layer used by GUI for RSI/TIM TCP, ClearCore UDP, and optional legacy paths. | `_init_rsi`, `_init_clearcore`, `_clearcore_translate`, `_init_myactuator`, `send_command`, `close` |
| `numeric_keypad.py` | Touch-friendly numeric keypad popup for value entry in GUI fields. | `NumericKeypad` helpers |
| `InitializeController.py` | INI-driven comm-object construction and query helper utility. | `_read_ini`, `_create_comm`, `query_all_axes` |
| `rmp_controller.py` | RapidCode wrapper utility module used for local diagnostics and wrapper-style testing flows. | `RMPController` methods |
| `RapidCodeHelpers.py` | Misc. RapidCode helper routines and reference utilities. | RapidCode helper functions |
| `ControllerGUI_github.py` | Alternate/sanitized GUI variant retained for repository use. | GUI event and layout routines |

### TIM iPC400 Runtime (Service Side)

| File | What It Does | Key Routines |
|------|--------------|--------------|
| `tim_service/tim_motion_service.py` | Service entrypoint; loads config, starts motion server, builds adapters/router/watchdog. | `load_config`, `main`, `on_stop`, `tick` |
| `tim_service/tim_motion_server.py` | TCP server on port 503 that receives Galil-like ASCII commands from GUI clients. | `run`, `_handle_client`, `shutdown` |
| `tim_service/tim_axis_router.py` | Axis-based command routing between RapidCode and ClearCore adapters. | `dispatch`, `_extract_axis`, `shutdown` |
| `tim_service/tim_rapidcode_adapter.py` | A-D adapter that translates command stream to RapidCode/EtherCAT API calls (enable, move, query, safety state handling). | `_init_rapidcode`, `handle_command`, `_handle_enable`, `_handle_start_motion`, `_handle_absolute_move`, `_handle_set_speed`, `_handle_query_position`, `shutdown` |
| `tim_service/tim_clearcore_adapter.py` | Axis E UDP adapter for ClearCore command/response translation. | `_init_clearcore`, `handle_command`, `_handle_absolute_move`, `_handle_set_speed`, `_handle_query_position`, `_handle_stop`, `shutdown` |
| `tim_service/tim_safety_watchdog.py` | Service-side safety monitor for activity timeout and fault state management. | `start`, `_watchdog_loop`, `_handle_timeout`, `update_activity`, `set_axis_enabled`, `set_axis_position`, `add_fault`, `shutdown` |
| `tim_service/rsi_network_probe.py` | RapidCode network diagnostics utility for bring-up and troubleshooting. | Probe and diagnostics routines |

### Shared Configuration and Persistent State

| File | Purpose |
|------|---------|
| `controller_config.ini` | GUI-side comm endpoints, axis scaling, limits, and descriptions. |
| `tim_service/tim_config.yaml` | Service-side host/port, adapter, and safety configuration. |
| `motion_defaults.json` | Persisted startup defaults for speed/accel/decel. |
| `sequence_state.json` | Persisted ALL-tab sequence values and repeat flags. |
| `controller_comm.log` / `tim_motion_service.log` | Runtime logs for diagnostics and fault/event traceability. |

### Startup and Launch Scripts

| File | Purpose |
|------|---------|
| `run_gui.ps1` | Launches GUI on workstation using local Python environment. |
| `start_tim.ps1` | Unified launcher for TIM service and/or GUI modes. |
| `start_tim_service.ps1` | Service-only wrapper entrypoint (delegates to `start_tim.ps1`). |

### Tests and Validation Utilities

| File | Purpose |
|------|---------|
| `test_comm.py` | Communications validation script. |
| `test_rmp_installation.py` | RapidCode installation and phantom-mode sanity test. |
| `tim_service/tests/test_axis_router.py` | Unit tests for axis routing behavior. |
| `tim_service/tests/test_mock_rapidcode.py` | Mock RapidCode fixtures for service testing without hardware. |
| `tim_service/examples/client_test.py` | Example TCP client for manual service command testing. |

### Ownership Summary

- **Laptop owns**: Operator interface, command intent generation, display/persistence UX.
- **iPC400 owns**: Motion execution authority for EtherCAT axes and service-level safety/watchdog logic.
- **Current hybrid note**: Axis E still has direct GUI UDP control path in active deployment; target architecture remains iPC400 ownership of all hardware I/O.

---

## Resolved Bugs & Key Debugging Lessons (2026-04-19)

### Bug 1 — Actuals always showed 0 (TCP buffer accumulation)
**Root cause**: The TIM service sends a response for *every* command (queries AND action commands). The old `CommMode1` `send_command` only called `recv()` for query commands. Responses to action commands (`SH`, `SP`, `AC`, `PA`, `BG` → each returning `"1"`) piled up in the TCP buffer. The polling thread read those stale `"1"` responses as position values → `1 ÷ 364.0888 ≈ 0.003°` → displayed as 0.

**Fix** (`communications.py`): `send_command` for CommMode1 now always calls `recv()` after every `sendall()`, inside `self._lock`. The lock is also held across the entire send+recv pair so the polling thread and GUI event loop cannot interleave on the same socket.

### Bug 2 — Polling thread crashed silently on first iteration (NameError)
**Root cause**: `torque_cmd`, `status_cmd`, `speed_cmd`, `torque_resp`, `status_resp`, `speed_resp` were used in the polling loop body but never initialized at the top of the `while` loop. `NameError` was raised on first iteration, caught silently by the outer `except Exception: pass`, and the thread exited permanently.

**Fix** (`ControllerPolling.py`): All eight command strings and response variables are initialized at the top of the `while` loop.

### Bug 3 — TCP connection dropped every 1–5 minutes (WinError 10054)
**Root cause**: Nagle's algorithm occasionally batched two client commands into one TCP segment. The old server `recv(256)` read both as one string, dispatched the combined string as a single command, and sent one response — leaving the protocol one response short and eventually misaligning the stream until the socket was reset.

**Fix** (`tim_motion_server.py`): `_handle_client` now uses a `_recv_line()` helper that accumulates bytes until `\n`, ensuring exactly one command is dispatched per server cycle regardless of TCP segmentation.

**Also added** (`communications.py`): `_reconnect_rsi()` auto-reconnect — if `sendall()` or `recv()` raises `OSError`, the broken socket is closed and one reconnect is attempted before returning `False`.

### Bug 4 — Actual position "drifted back to zero" after motor stopped
**Root cause**: The GUI's `_consecutive_zero_actuals` counter forced the display to `'0'` after 3 consecutive zero-valued position responses. RapidCode/EtherCAT briefly returns 0 during the state transition at the end of a `MoveSCurve` profile (MOVING → DONE). Three polling cycles at 500 ms = 1.5 s was enough to trip the counter.

**Fix** (`ControllerGUI.py`): The zero-suppression logic now only forces `'0'` when:
- the commanded setpoint **is** zero (`last_setpoint_zero`), OR
- the motor has **never** been at a non-zero position (`has_seen_nonzero = False`)

Otherwise, the last valid non-zero reading is held on screen. The `consecutive_zero` counter no longer overrides the display.

### Bug 5 — BG command auto-enabled a disabled axis
**Root cause**: `_handle_start_motion` in `tim_rapidcode_adapter.py` contained deliberate auto-enable logic: if the axis was disabled when `BG` arrived, it silently called `_handle_enable()` before executing the move.

**Fix**: BG on a disabled axis now returns `"0"` and logs a warning. The operator must explicitly enable the axis before issuing motion commands.

### EtherCAT startup latency (~30 s)
After the GUI connects to the TIM service, `ActualPositionGet()` returns 0 for approximately 30 seconds while the EtherCAT network cycles through INIT → PRE-OP → SAFE-OP → OPERATIONAL states. This is expected hardware behavior — the GUI now handles it cleanly by showing `'0'` until the first real encoder reading arrives.

---

## Future Enhancements

### Phase 2: Protocol Simplification
Replace Galil-like commands with cleaner TIM API once motion is proven stable.

### Phase 3: Real-Time Kernel (Optional)
If coordination between A-D and E is required below 500 ms, consider PREEMPT_RT Linux or Windows RT kernel on iPC400.

### Phase 4: Multi-Axis Coordination
Implement S-curve blending, circular interpolation, or PVT (position-velocity-time) streaming across A-D axes if needed.

### Phase 5: Fault Diagnostics Dashboard
Extend GUI to capture and display RapidCode fault codes and ClearCore diagnostic telemetry.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| iPC400 motion service crashes | Auto-restart via Windows Service, watchdog disables servos |
| Network disconnect | iPC400 watchdog triggers stop, motion state held locally |
| Operator loses GUI | iPC400 continues executing queued motion, remains safe |
| EtherCAT slave missing | RapidCode returns error; service stops motion and sets fault |
| ClearCore board offline | Service handles UDP timeout, reports axis E as offline |
| GUI sends invalid command | iPC400 validates and rejects, logs error for operator |

---

## References

- **RSI RapidCode Docs**: C:\RSI\10.7.1\Documentation\
- **EtherCAT Standard**: IEC 61158-12
- **Teknic ClearCore Docs**: https://www.teknic.com/products/clearcore/
- **MyActuator RMD-X10**: https://www.myactuator.com/rmd-x10

---

## Document History

| Date | Version | Notes |
|------|---------|-------|
| 2026-04-11 | 1.0 | Initial system design specification |
| 2026-04-18 | 1.1 | Added 10,000 ft software inventory: active files, key routines, startup scripts, tests, and ownership map |
| 2026-04-19 | 1.2 | Added encoder/scaling reference table; updated axis config section with correct 364.0888 constants; added Resolved Bugs section documenting TCP buffer, NameError, connection drop, zero-drift, and auto-enable fixes |
