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

Or use the preferred launcher scripts from the repo root:

```powershell
# Combined launcher (service + optional GUI)
.\start_tim.ps1

# Service only
.\start_tim_service.ps1
```

## Configuration

### Axis parameters — `controller_config.ini` (repo root)

Axis calibration, limits, and speed/accel settings are mastered in **`controller_config.ini`**
at the repo root. The GUI automatically pushes these values into `tim_config.yaml` on the
iPC400 at every startup via the network share — no manual file copying needed.

The yaml axes sections are overwritten on each GUI start. Do not edit them manually.

**Calibration constant for Axes A–D (MyActuator RMD EtherCAT motors):**

```
Motor:    RMD-X12 / RMD-X8, P20 variant (20:1 planetary gearbox)
Encoder:  17-bit absolute (2^17 = 131,072 counts/revolution)
Firmware: EtherCAT firmware handles the gearbox internally and reports
          position as if the encoder sits on the output shaft.

scaling = 131072 / 360 = 364.0888 counts per output degree
gearbox = 1  (gearbox is invisible to RapidCode — do not change)
```

Verified empirically: 360° command in RapidSetup with UserUnitsSet=364.0888 = exactly 1 output revolution.

**Axis E note:** Axis E (ClearCore) is controlled directly by the GUI via UDP —
it does not route through this service. Its parameters are synced to the yaml for
consistency but are not used for live motion today.

### Service settings — `tim_config.yaml`

Edit `tim_config.yaml` for service-level settings only:
- EtherCAT interface name
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

## Healthy Startup Log (what to expect)

When the service starts cleanly against real hardware, you should see these events in order in `tim_motion_service.log`:

```
TIM Motion Service Starting
TCP server listening on 0.0.0.0:503
RapidCode network starting...
EtherCAT network state: 260          ← must reach 260 (OPERATIONAL)
OperationModeSet(CSP=8) axis A       ← CSP set after network is OPERATIONAL
OperationModeSet(CSP=8) axis B
OperationModeSet(CSP=8) axis C
OperationModeSet(CSP=8) axis D
ClearCore adapter ready (192.168.1.171:8888)
Waiting for client connection...
```

If `OperationModeSet` appears **before** state 260, or the network stalls at state 256 (SAFE-OP), motion will appear to work but produce no output — restart the service and wait for state 260 before issuing any CSP commands.

## Field-Proven Bring-Up Notes

These notes capture what was required to get real hardware motion working (GUI laptop + iPC400 service, 2026-04-17).

### 1) EtherCAT drive mode ordering matters
- `OperationModeSet(CSP=8)` must be applied **after** `NetworkStart()` reaches OPERATIONAL (`state 260`).
- Setting CSP while network is pre-op/safe-op can appear successful but produce no motion.

### 2) Units must be explicit and consistent
- For A/B with current gearing/scaling, service uses `UserUnitsSet(4500.0 counts/deg)`.
- Adapter logic tracks user-units mode per axis and falls back to native units when unavailable.

### 3) Axis enable/fault recovery must tolerate transient states
- Real hardware may throw transient STOPPING/ClearFaults errors during enable.
- Service enable flow retries and treats some pre-enable clear-fault failures as recoverable.

### 4) Bench setup may require temporary limit policy changes
- During bench bring-up (motors not installed), GUI limit-stop enforcement was temporarily disabled to avoid false trips.
- Re-enable limits before installed operation.

### 5) Fault-clear from GUI is available
- GUI `Clear Faults` button routes to service and RapidCode fault-clear handling for A-D.

### 6) Startup usability
- GUI persists and restores per-servo `speed`, `accel`, and `decel` values across sessions.
- `Reset Tuning` button restores all servos to `10/10/10`.

### Quick verification checklist
1. Start TIM service on iPC400 and confirm network reaches state `260`.
2. Confirm logs show per-axis `OperationModeSet(CSP=8)` after network startup.
3. Enable axis and issue a small absolute move (e.g., 10 deg).
4. Verify position readback updates and no persistent fault state remains.

## Reversing Axis Direction

Some motors are mounted so that increasing encoder counts move in the physically *wrong* direction (e.g., the motor naturally reads 180° at start-of-travel and 0° at end-of-travel, but you want the user to see 0° at start and 180° at end).  This is corrected entirely in software — no hardware or drive configuration changes are needed.

### How to enable it

Add `reverse: true` to the axis entry in `tim_config.yaml`:

```yaml
rapidcode:
  axes:
    A:
      name: Primary Rotation X12
      scaling: 364.0888
      gearbox: 1.0
      min_pos: 0
      max_pos: 180
      software_limit_deg: 180
      reverse: true        # ← add this line
```

Restart the service.  No other files need to change.

### What it does

The adapter applies a single linear transform at two points:

| Operation | Formula |
|---|---|
| Outgoing setpoint (PA command) | `motor_target = max_pos − user_setpoint` |
| Incoming position readback | `user_pulses = max_pos × scale − raw_pulses` |
| Relative move (PR command) | distance sign is negated |

`max_pos` is read from the axis config, so if you ever extend the travel range, update `max_pos` and the inversion automatically follows — no code change required.

**Example — Axis A (Primary Rotation, max_pos = 180°):**

| Physical position | Motor encoder (°) | User display (°) |
|---|---|---|
| Top of backswing | 180 | 0 |
| Address / impact | 90 | 90 |
| Finish | 0 | 180 |

### How it interacts with Zero Position

The `Zero Position` button stores the current raw encoder value as an offset so you can fine-tune the reference point without touching the drive.  With a reversed axis the semantics are the same — press Zero Position when the axis is at the physical location you want to call 0° **in motor space** (i.e., at `max_pos` in user space, which is the finish end of travel).  The inversion then maps that offset correctly through all subsequent moves and readbacks.

The offset is persisted to `tim_position_offsets.json` beside the service files and restored automatically on every restart.

### Applying to other axes

To reverse any other axis (B, C, D) follow the same steps:

1. Add `reverse: true` to that axis's block in `tim_config.yaml`.
2. Verify the `max_pos` value is correct for that axis (it is the denominator of the inversion).
3. Restart the service and confirm that the GUI's Actual Position reads the expected value at each end of travel.
4. Re-run Zero Position if the reference needs adjustment.

No code changes are required — the `_is_reversed()` check in `tim_rapidcode_adapter.py` applies to any axis whose config contains `reverse: true`.

## Testing

Run unit tests:

```powershell
pip install pytest pytest-cov
pytest tests/ -v --cov
```

## Development Workflow

### Editing Code from Your Laptop

The recommended workflow is to edit service files on your laptop and push to GitHub, then pull on the iPC400.

1. **Edit code on your laptop** in VS Code (`d:\Python\ControllerGUI\tim_service`)
2. **Test locally** with phantom mode (`--phantom` flag)
3. **Push to GitHub** from your laptop
4. **Pull on iPC400** and run with real hardware when ready

### Network Share (Edit Live on iPC400)

If you want to edit files directly on the iPC400 without a push/pull cycle, set up a Windows network share.

**Network addresses:**
- Engineering workstation (laptop): `192.168.1.150`
- iPC400 (TIM-PC): `192.168.1.151`
- ClearCore (Axis E): `192.168.1.171:8888`

**On the iPC400:**
1. Right-click `C:\TIM\ControllerGUI` → Properties → Sharing → Advanced Sharing
2. Check "Share this folder", set share name (e.g., `TIM_Service`)
3. Permissions → Grant Read/Write to your laptop user

**On your laptop:**
- Map a network drive to `\\192.168.1.151\TIM_Service` (File Explorer → This PC → Map network drive)
- Or open directly in VS Code: File → Open Folder → type `\\192.168.1.151\TIM_Service`

**Troubleshooting the share:**
```powershell
ping 192.168.1.151
Test-NetConnection 192.168.1.151 -Port 503
```
- "Access Denied" — check share permissions on iPC400
- "Network path not found" — use IP address instead of hostname

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

## Troubleshooting

### "Cannot import RSI.RapidCode" / "Cannot import RapidCodePython"
- Verify RSI RapidCode 10.7.1+ is installed on the iPC400 at `C:\RSI\10.7.1\`
- Add the RSI path to VSCode `settings.json` on the iPC400:
  ```json
  {
      "python.autoComplete.extraPaths": ["C:\\RSI\\10.7.1"],
      "python.analysis.extraPaths":    ["C:\\RSI\\10.7.1"]
  }
  ```
- Verify: `python -c "import RapidCodePython"`

### Service won't connect / EtherCAT not starting
- Close RapidSetup — only one process can own the EtherCAT network at a time
- Confirm service is listening: `netstat -ano | findstr :503`
- Check `tim_motion_service.log` for the error detail

### Motion not working (axes enable but don't move)
- Confirm `OperationModeSet(CSP=8)` was applied after network reached state `260` (see bring-up notes above)
- Verify user-units are set (`UserUnitsSet(4500.0)` for A/B with current gearing)
- Check `tim_motion_service.log` for fault or pre-enable errors

### GUI shows "No Link" for A-D
- Confirm TIM service is running on iPC400: `netstat -ano | findstr :503`
- Test from GUI PC: `Test-NetConnection 192.168.1.151 -Port 503`

## See Also

- [TIM_SYSTEM_DESIGN.md](../TIM_SYSTEM_DESIGN.md) — overall system architecture
- [ControllerGUI README](../README.md) — GUI-side documentation
