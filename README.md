# ControllerGUI - Multi-Axis Motion Controller Interface

A touchscreen-friendly GUI application for controlling 8-axis motion systems with support for mixed controller types (Galil DMC-4180 + MyActuator RMD-X8 motors).

## System Overview

**ControllerGUI** provides a unified interface for:
- **Axes A-G**: Galil DMC-4180 EtherCAT controller
- **Axis H**: MyActuator RMD-X8 servo motor (via CAN-to-Ethernet)

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

## System Requirements

### Hardware
- **Galil DMC-4180** EtherCAT motion controller (for axes A-G)
- **MyActuator RMD-X8** servo motor (for axis H)
- **Waveshare CAN-to-Ethernet** converter (for MyActuator)
- Windows PC with network connectivity

### Software
- **Windows 10/11**
- **Python 3.10** (required for RapidCode/RMP compatibility)
- **NumPy 1.22.0** (required for RapidCode)
- **Optional**: RapidCode/RMP 10.7.1+ (if using CommMode4)

### Python Packages
- `FreeSimpleGUI` - GUI framework
- `pyserial` - Serial communications
- `numpy==1.22.0` - Required for RMP
- `gclib` (optional) - Galil communications library

---

## TIM Motion Service (iPC400)

The **TIM Motion Service** is the motion control gateway that runs on the iPC400 (TIM-PC) and owns all hardware I/O.

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

### 1. Install Python 3.10

Download and install Python 3.10 from [python.org](https://www.python.org/downloads/)

Verify installation:
```powershell
py -3.10 --version
```

### 2. Create Virtual Environment

Navigate to the project directory and create a Python 3.10 virtual environment:

```powershell
cd D:\Python\ControllerGUI
py -3.10 -m venv venv_py310
```

### 3. Activate Virtual Environment

```powershell
.\venv_py310\Scripts\Activate.ps1
```
python ControllerGUI.py


You should see `(venv_py310)` in your terminal prompt.

### 4. Install Dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install numpy==1.22.0
python -m pip install FreeSimpleGUI
python -m pip install pyserial
```

### 5. Install Galil gclib (Optional)

Download and install gclib from [Galil](https://www.galil.com/downloads/software) if using CommMode1 (Galil Ethernet).

### 6. Install RapidCode/RMP (Optional)

If planning to use CommMode4 (RMP):
1. Download RMP 10.7.1+ from RSI
2. Install to `C:\RSI\10.7.1`
3. Verify RapidCode imports:
   ```powershell
   python test_rmp_installation.py
   ```

---

## Configuration

### controller_config.ini

Edit `controller_config.ini` to configure your hardware:

```ini
[Controller]
type = DMC-4180

[CommMode1]
address = 192.168.4.177          # Galil controller IP

[CommMode5]
ip = 192.168.0.7                 # MyActuator CAN-to-Ethernet IP
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
.\venv_py310\Scripts\Activate.ps1
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

```
ControllerGUI/
├── ControllerGUI.py           # Main GUI application
├── ControllerPolling.py       # Background position polling thread
├── communications.py          # Unified controller communications
├── numeric_keypad.py          # Touchscreen numeric input
├── controller_config.ini      # Hardware configuration
├── test_rmp_installation.py   # RMP installation validator
├── test_myactuator.py         # MyActuator test utility
├── venv_py310/                # Python 3.10 virtual environment
└── README.md                  # This file
```

### Key Modules

- **ControllerGUI.py**: Main application with tabbed interface
- **communications.py**: Multi-mode controller abstraction
  - CommMode1: Galil Ethernet (gclib)
  - CommMode2: Galil Serial
  - CommMode3: ClearCore UDP
  - CommMode4: RapidCode/RMP
  - CommMode5: MyActuator CAN-to-Ethernet
- **ControllerPolling.py**: Background thread for position updates
- **numeric_keypad.py**: Custom numeric input dialog

---

## Controller Communication Modes

### CommMode1 - Galil Ethernet (gclib)
- Uses Galil's gclib library
- Direct Ethernet connection to DMC controller
- Supports all Galil command set

### CommMode5 - MyActuator CAN-to-Ethernet
- TCP connection to Waveshare CAN-to-ETH converter
- Translates Galil-like commands to MyActuator CAN protocol
- Position control mode with speed limits
- Encoder position feedback

### Routing Logic
- Axes A-G → Galil controller (CommMode1)
- Axis H → MyActuator motor (CommMode5)

---

## Troubleshooting

### GUI won't start
- Verify virtual environment is activated: `(venv_py310)` in prompt
- Check Python version: `python --version` should show 3.10.x
- Reinstall packages: `pip install -r requirements.txt`

### "Cannot connect to controller"
- Verify controller IP addresses in `controller_config.ini`
- Check network connectivity: `ping 192.168.4.177`
- Ensure controller is powered on

### Position not updating
- Check "Show Poll Logs" to see if polling is active
- Verify encoder connections on hardware
- Check debug log for error messages

### MyActuator (Axis H) not responding
- Verify CAN-to-Ethernet IP and port in config
- Check MyActuator motor ID matches config
- Test connection: `python test_myactuator.py`

### RMP/RapidCode import fails
- Ensure Python 3.10 (not 3.12) is active
- Install NumPy 1.22.0: `pip install numpy==1.22.0`
- Verify RMP installed: `C:\RSI\10.7.1\`
- Run test: `python test_rmp_installation.py`

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
- CommMode1 (Ethernet) and CommMode2 (Serial) support

---

## Author & Support

**Author**: gskovira01  
**Repository**: https://github.com/gskovira01/ControllerGUI

For issues or questions, please open a GitHub issue or contact the development team.

---

## License

Internal Use Only