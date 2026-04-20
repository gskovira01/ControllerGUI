# ControllerGUI - TIM Multi-Axis Motion Interface

Touchscreen-friendly operator GUI for TIM with mixed routing:
- Axes A-D: iPC400 TIM Motion Service (TCP/503)
- Axis E: ClearCore UDP (direct from GUI in current deployment)
- Axes F-G: future spare (reserved)
- Axis H: legacy MyActuator path (optional / not primary for TIM)

## System Overview

**ControllerGUI** provides a unified interface for:
- **Axes A-D**: RSI RapidCode/EtherCAT via TIM Motion Service on iPC400
- **Axis E**: Teknic ClearCore over UDP
- **Axes F-G**: future spare (reserved for expansion)
- **Axis H**: legacy MyActuator CAN-over-Ethernet (optional)

### Key Features
- Tabbed interface for 8 independent servo controls
- Real-time position monitoring (2 Hz polling)
- Jog controls (continuous motion)
- Absolute and relative positioning
- Speed, acceleration, and deceleration control
- Enable/disable per axis
- Zero position setting
- Numeric keypad for touchscreen input
- Debug logging with optional poll message display
- Mixed-mode controller support

---

## Significant Documents

Use this index as the quick entry point for architecture, startup, and integration context:

1. [README.md](README.md) - Main operator/developer entry point for this repo.
2. [TIM_SYSTEM_DESIGN.md](TIM_SYSTEM_DESIGN.md) - System architecture, deployment model, and 10,000 ft software inventory.
3. [tim_service/README.md](tim_service/README.md) - TIM service setup, operation, bring-up notes, and network share workflow.

---

## System Requirements

### Hardware
- **iPC400 (TIM-PC)** running TIM Motion Service (A-D gateway)
- **A-D EtherCAT motors** (e.g., X12/X8) owned by iPC400/RapidCode
- **ClearCore + Teknic servo** for Axis E (UDP endpoint)
- Optional: **Waveshare CAN-to-Ethernet** path for legacy Axis H
- Windows PC with network connectivity

### Software
- **Windows 10/11**
- **Python 3.11+** (3.10 supported as fallback)
- **FreeSimpleGUI**
- **NumPy**
- Optional on iPC400 only: RapidCode/RMP for hardware-backed A-D service

### Python Packages

#### GUI Runtime (engineering workstation)
- `FreeSimpleGUI` - GUI framework
- `pyserial` - utility serial support
- `numpy` - math/data utilities

#### TIM Service Runtime (iPC400)
- `pyyaml` - TIM service configuration parsing (`tim_config.yaml`)
- `numpy` (`>=1.22.0,<2`) - RapidCode-compatible NumPy ABI for service/hardware integration
- `python-daemon` - service wrapper helpers
- `pywin32` - Windows-specific service/runtime integration

#### Optional Features
- `openpyxl` - Excel DataPipe/PVT file loading in GUI workflows
- RSI RapidCode Python modules (`RapidCodePython` / `RSI.RapidCode`) - installed via RSI installer, not pip

#### Test/Development
- `pytest` - unit test runner
- `pytest-cov` - test coverage reporting

---

## TIM Motion Service (iPC400)

The **TIM Motion Service** is the A-D motion gateway on iPC400.

Current deployment note:
- A-D are expected through TIM Motion Service on `192.168.1.151:503`.
- Axis E is currently controlled directly by GUI via ClearCore UDP (`192.168.1.171:8888`).

**See [tim_service/README.md](tim_service/README.md)** for:
- Service architecture and startup
- Configuration and deployment
- Testing with phantom/mock hardware
- Network share setup (edit code from your laptop)

Quick start:
```powershell
cd tim_service
python tim_motion_service.py --phantom --debug
```

---

## Installation & Setup

### 1. Install Python 3.11

Download and install Python 3.11 from [python.org](https://www.python.org/downloads/)

Verify installation:
```powershell
py -3.11 --version
```

### 2. Engineering Workstation (GUI) Setup

Create and activate GUI virtual environment:

```powershell
cd D:\Python\ControllerGUI
py -3.11 -m venv venv_rmp311
.\venv_rmp311\Scripts\Activate.ps1
```

Fallback (if 3.11 is unavailable):

```powershell
cd D:\Python\ControllerGUI
py -3.10 -m venv venv_py310
.\venv_py310\Scripts\Activate.ps1
```

Install GUI dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install numpy==1.22.0
python -m pip install FreeSimpleGUI
python -m pip install pyserial
python -m pip install openpyxl
```

Run GUI:

```powershell
python ControllerGUI.py
```

### 3. iPC400 TIM Service Setup

Create and activate service virtual environment:

```powershell
cd C:\TIM\ControllerGUI\tim_service
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
```

Install service dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install RapidCode/RMP on iPC400 for real A-D hardware operation:
1. Install RSI RapidCode/RMP on iPC400.
2. Verify service-side imports (`RapidCodePython` / `RSI.RapidCode`) resolve.

### 4. Optional Test/Dev Dependencies

If you want to run tests locally:

```powershell
python -m pip install pytest pytest-cov
```

---

## Configuration

### controller_config.ini — single source of truth

`controller_config.ini` is the master configuration file for all axis parameters.
Edit axis parameters here — the GUI pushes them automatically to the TIM service
yaml on iPC400 at startup via the network share. No manual file copying required.

**How sync works:**
1. GUI starts on laptop → reads `controller_config.ini`
2. GUI writes axis values into `tim_config.yaml` on iPC400 (via network share path set in `[CommMode1] tim_yaml_path`)
3. TIM service reads its yaml as normal — always up to date

**Axis E note:** Axis E (ClearCore) is controlled directly by the GUI via UDP and does
not go through the TIM service. Its INI parameters are still synced to the yaml for
consistency but are not used for live motion routing today.

**Calibration constant for Axes A–D (MyActuator RMD EtherCAT motors):**
```
scaling = 364.0888   (= 131072 / 360 = 2^17 counts per output degree)
gearbox = 1          (EtherCAT firmware handles the 20:1 gearbox internally)
```
The motor has a 17-bit absolute encoder (131,072 counts/rev). The EtherCAT firmware
applies the 20:1 gearbox ratio internally and reports position at the output shaft.
Verified empirically: 360° command in RapidSetup = exactly 1 output revolution.

```ini
[Controller]
type = RSI_PC400

[CommMode1]
type = RSI
ip_address = 192.168.1.151       # iPC400 TIM Motion Service (A-D)
port = 503
protocol = TCP

[CommMode6]
type = ClearCore
ip_address = 192.168.1.171       # ClearCore axis E (current direct GUI path)
port = 8888
protocol = UDP
disable_cmd = S1B1 DISABLE
stop_cmd = S1B2 STOP

[CommMode5]
ip = 192.168.0.7                 # Legacy optional Axis H path
port = 20001
motor_id = 1

[AXIS_A]
description = Primary
min = 0
max = 180
pulses = 7200
degrees = 360
scaling = 20.0
gearbox = 15
speed_min = 0
speed_max = 360
accel_min = 0
accel_max = 720
decel_min = 0
decel_max = 720

[AXIS_H]
description = MyActuator Motor
min = -180
max = 180
pulses = 36000
degrees = 360
scaling = 100.0
gearbox = 1
speed_min = 0
speed_max = 500
accel_min = 0
accel_max = 500
decel_min = 0
decel_max = 500
```

**Key Parameters:**
- `scaling`: Encoder counts per motor revolution
- `gearbox`: Gear ratio (if applicable)
- `min/max`: Software position limits (degrees)
- `speed_max/accel_max/decel_max`: Maximum values for motion parameters

---

## Running the Application

### 1. Activate Virtual Environment
```powershell
.\venv_rmp311\Scripts\Activate.ps1
```

### 2. Launch GUI
```powershell
python ControllerGUI.py
```

### 3. Using the GUI

**Per-Axis Controls:**
- **Enable/Disable**: Servo power control
- **Speed**: Motion velocity (degrees/second)
- **Acceleration/Deceleration**: Motion profiles (degrees/second²)
- **Absolute Position**: Move to specific angle
- **Relative Position**: Move by offset from current position
- **Jog CW/CCW**: Continuous motion while button held
- **Zero Position**: Set current position as 0°
- **Stop Motion**: Emergency stop

**Display:**
- **Actual Position**: Real-time encoder position (DEG and PUL)
- **Status Light**: Green=Enabled, Yellow=Disabled, Gray=Unknown

**Debug Log:**
- Toggle "Show Poll Logs" to see position polling messages
- All commands and responses logged for troubleshooting

---

## File Structure

### Where to Find Files

- **ControllerGUI.py** — The main program you run for the GUI.
- **ControllerPolling.py** — Handles checking controller status in the background.
- **communications.py** — Code for talking to hardware (serial/network).
- **numeric_keypad.py** — The pop-up keypad for entering numbers in the GUI.
- **controller_config.ini** — The main settings file for the GUI.
- **sequence_state.json** — Remembers your last speed/accel/decel settings.
- **archive/** — Old backups and extra tools. Look here for previous versions and non-core scripts.
- **tim_service/** — All the code that runs on the iPC400 (motion service, adapters, safety, etc).
- **venv_rmp311/** — Python 3.11 environment (use this for normal work).
- **venv_py310/** — Python 3.10 environment (fallback only).
- **wheels/** — Local copies of Python packages for offline install.

### Key Modules

- **ControllerGUI.py**: Main application with tabbed interface
- **communications.py**: Multi-mode controller abstraction
  - CommMode1: RSI/TIM service TCP (A-D)
  - CommMode6: ClearCore UDP (E)
  - CommMode5: MyActuator CAN-to-Ethernet (H, optional)
- **ControllerPolling.py**: Background thread for position updates
- **numeric_keypad.py**: Custom numeric input dialog

---

## Controller Communication Modes

### CommMode1 - RSI/TIM TCP (A-D)
- TCP client to TIM Motion Service on iPC400
- Uses Galil-like ASCII command compatibility layer
- Intended path for A-D EtherCAT control

### CommMode6 - ClearCore UDP (E)
- UDP command/response path to ClearCore
- Active in current deployment for Axis E
- Planned migration target: routed through TIM service

### CommMode5 - MyActuator CAN-to-Ethernet
- TCP connection to Waveshare CAN-to-ETH converter
- Legacy/optional path for Axis H

### Routing Logic
- Axes A-D → TIM Motion Service over CommMode1
- Axis E → ClearCore over CommMode6 (current)
- Axis H → MyActuator over CommMode5 (optional)

---

## Troubleshooting

### GUI won't start
- Verify virtual environment is activated: `(venv_py310)` in prompt
- Check Python version: `python --version` should show 3.11.x (or 3.10.x fallback)
- Reinstall packages: `pip install -r requirements.txt`

### "Cannot connect to controller"
- Verify controller IP addresses in `controller_config.ini`
- Check A-D gateway connectivity: `ping 192.168.1.151`
- Check Axis E endpoint connectivity: `ping 192.168.1.171`
- Ensure iPC400 TIM service is running on port `503` for A-D

### Position not updating
- Check "Show Poll Logs" to see if polling is active
- Verify encoder connections on hardware
- Check debug log for error messages

### MyActuator (Axis H) not responding
- Verify CAN-to-Ethernet IP and port in config
- Check MyActuator motor ID matches config
- Test connection: `python test_myactuator.py`

### A-D still shows No Link
- Confirm TIM service is listening on iPC400: `netstat -ano | findstr :503`
- Test from GUI PC: `Test-NetConnection 192.168.1.151 -Port 503`
- Close RapidSetup before GUI A-D control tests (single hardware owner)

### "Access Denied" during RMP installation
- Run installer as Administrator
- Install to C:\ instead of D:\ to avoid permission issues
- Reboot after installation

### Too many terminals open in VS Code
- **Quick Fix**: Press `Ctrl+Shift+P` → Type "Terminal: Kill All Terminals" → Press Enter
- **Alternative**: Right-click in terminal area → Select "Kill All Terminals"
- **Manual**: Click trash can icon 🗑️ next to each terminal name in dropdown
- **Prevention**: Reuse existing terminals; close terminals when done

---

## Development Notes

### Polling Rate
Default: 2 Hz (500ms interval)
- Configurable in `ControllerPolling.py` (`time.sleep(0.5)`)
- Higher rates increase network traffic
- Lower rates reduce responsiveness

### Debug Messages
Console debug output controlled in `communications.py`:
- Polling messages: Commented out by default
- Motion commands: Active for troubleshooting

### Position Limits
Software limits enforced in GUI:
- Prevents moves beyond configured min/max
- Stops motion if position exceeds limits during external control

---

## Safety Considerations

⚠️ **IMPORTANT SAFETY NOTES:**

1. **Always wire an external E-stop** when using real hardware
2. **Test with disabled motors** before enabling
3. **Start with low speeds** and gradually increase
4. **Monitor actual position** during all moves
5. **Keep clear of moving parts** during operation
6. **Verify soft limits** match physical constraints
7. **Have emergency stop procedures** documented

---

## Version History

### v1.3.0 - January 18, 2026
- Added MyActuator RMD-X8 support (Axis H, CommMode5)
- Fixed Axis H position polling routing
- Optimized polling rate to 2 Hz
- Cleaned up console debug output
- Added default absolute position of 0 on startup

### v1.2.0 - December 14, 2025
- Tabbed interface improvements
- Background polling thread implementation
- Enhanced error handling

### v1.0.0 - Initial Release
- Basic 8-axis Galil control
- Historical at launch: CommMode1 (Ethernet) and CommMode2 (Serial) support

---

## Author & Support

**Author**: gskovira01  
**Repository**: https://github.com/gskovira01/ControllerGUI

For issues or questions, please open a GitHub issue or contact the development team.

---

## License

Internal Use Only