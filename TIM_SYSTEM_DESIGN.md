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

### Current Configuration (controller_config.ini)

```ini
[Controller]
type = RSI_PC400

[CommMode1]
# iPC400 motion service (axes A-D: RapidCode/EtherCAT)
type = RSI
ip_address = 192.168.1.151
port = 503
protocol = TCP

[CommMode6]
# ClearCore board (axis E: UDP, currently controlled directly by GUI)
type = ClearCore
ip_address = 192.168.1.171
port = 8888
protocol = UDP

[AXIS_A]
description = Primary Rotation
min = 0
max = 180
pulses = 108000
degrees = 360
scaling = 300.0
gearbox = 15

[AXIS_B]
description = Secondary Rotation
min = 0
max = 180
pulses = 108000
degrees = 360
scaling = 300.0
gearbox = 15

[AXIS_C]
description = Tertiary Rotation
min = 0
max = 160
pulses = 108000
degrees = 360
scaling = 300.0
gearbox = 15

[AXIS_D]
description = Quaternary (Tertiary Lift)
min = 0
max = 160
pulses = 108000
degrees = 360
scaling = 300.0
gearbox = 15

[AXIS_E]
description = Address Angle (ClearCore Servo 5)
min = 0
max = 45
pulses = 7200
degrees = 360
scaling = 1870
gearbox = 1

[AXIS_F]
description = (Unused)

[AXIS_G]
description = (Unused)

[AXIS_H]
description = Legacy CAN Motor (Disabled)
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
