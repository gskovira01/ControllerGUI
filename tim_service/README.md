# TIM Motion Service

**TIM Motion Service** is the motion control gateway for the TIM system.
It runs on the iPC400 (TIM-PC) and is the sole authority for all motion I/O.

## Structure

```
tim_service/
├── tim_motion_service.py        # Main entry point
├── tim_motion_server.py         # TCP socket server (port 503)
├── tim_axis_router.py           # Command dispatcher (routes by axis)
├── tim_rapidcode_adapter.py     # RapidCode wrapper (axes A-D)
├── tim_clearcore_adapter.py     # ClearCore wrapper (axis E)
├── tim_safety_watchdog.py       # Fault & watchdog manager
├── tim_config.yaml              # Service configuration
├── requirements.txt             # Python dependencies
├── tests/
│   ├── test_mock_rapidcode.py   # Mock RapidCode for testing
│   └── test_axis_router.py      # Router unit tests
├── examples/
│   └── client_test.py           # Example TCP client for testing
└── README.md                    # This file
```

## Quick Start

### 1. Install Dependencies

```powershell
cd C:\TIM\tim_service
pip install -r requirements.txt
```

### 2. Run in Phantom Mode (No Hardware)

For testing without RapidCode or ClearCore hardware:

```powershell
python tim_motion_service.py --phantom --debug
```

You should see:
```
TIM Motion Service Starting
TCP server listening on 0.0.0.0:503
```

### 3. Test with TCP Client

In another terminal, run the test client:

```powershell
python examples/client_test.py
```

This sends sample commands (enable, move, query) and prints responses.

### 4. Run with Real Hardware (iPC400 Only)

When RapidCode is installed and EtherCAT hardware is connected:

```powershell
python tim_motion_service.py --config tim_config.yaml
```

## Configuration

Edit `tim_config.yaml` to set:
- Axis names and limits
- ClearCore IP/port (192.168.1.171:8888)
- Safety parameters (watchdog timeout, motion limits)
- Development flags (phantom mode, verbose logging)

## Protocol

### Command Format

Galil-like ASCII commands with `\r\n` terminator:

```
SH A          # Enable axis A
MO A          # Disable axis A
PA A=45       # Move axis A to 45 degrees
PR A=10       # Move axis A by 10 degrees (relative)
SP A=100      # Set axis A speed to 100 DPS
TP A          # Query axis A target position
MG _RPA       # Query axis A actual position
MG _MO A      # Query axis A enable/disable status
ST A          # Stop axis A
DP A          # Clear (zero) axis A position
```

### Response Format

Numeric response (single value per line):
```
45.0
1
0
```

## Testing

Run unit tests:

```powershell
pip install pytest pytest-cov
pytest tests/ -v --cov
```

## Development Workflow

1. **Edit code on your laptop** in VS Code (d:\Python\ControllerGUI\tim_service)
2. **Test locally** with phantom mode (--phantom flag)
3. **Push to GitHub** from your laptop
4. **Pull on iPC400** and run with real hardware when ready

## Architecture

```
GUI PC (Operator)
    └─ TCP/503 ──────────→ TIM Motion Service (iPC400)
                               ├─ RapidCode Adapter (A-D)
                               │   └─→ EtherCAT/Axes A-D
                               └─ ClearCore Adapter (E)
                                   └─→ UDP/Axis E
```

## Safety Features

- **Watchdog timeout**: Auto-stop if client disconnects (10s default)
- **Motion timeout**: Force stop if motion exceeds max duration
- **Enable interlocks**: Axis must be enabled before move
- **Software limits**: Position clamped to min/max per axis
- **Fault logging**: All errors logged with axis/timestamp

## Next Steps

1. Install VS Code on iPC400 (if not already done)
2. Clone the repo on iPC400 → `C:\TIM\`
3. Edit `tim_config.yaml` with your network settings
4. Update RapidCode adapter methods (currently TODO placeholders) with real RapidCode calls
5. Test with real hardware via GUI client

## See Also

- [TIM_SYSTEM_DESIGN.md](../TIM_SYSTEM_DESIGN.md) — overall system architecture
- [ControllerGUI README](../README.md) — GUI-side documentation
- [RMP_QUICK_START.md](../RMP_QUICK_START.md) — RapidCode integration guide
