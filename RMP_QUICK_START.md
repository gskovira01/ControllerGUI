# RMP Integration Quick Start Guide
## For ControllerGUI Project

---

## What Was Created

I've integrated RMP (RapidCode Motion Platform) into your existing ControllerGUI project:

### New Files Created:
1. **[rmp_controller.py](rmp_controller.py)** - Main RMP wrapper class
   - Provides similar API to gclib for easy migration
   - Supports phantom axes (testing) and hardware modes
   - Includes PVT streaming for smooth trajectories

2. **[test_rmp_installation.py](test_rmp_installation.py)** - Installation verification
   - Tests RMP installation
   - Verifies phantom axes work
   - Tests the wrapper class

### Modified Files:
1. **[communications.py](communications.py)**
   - Added CommMode4 support for RMP
   - Integrated with existing architecture

2. **[controller_config.ini](controller_config.ini)**
   - Added [CommMode4] section
   - Configuration for testing/hardware modes

3. **[InitializeController.py](InitializeController.py)**
   - Added support for CommMode4 initialization

---

## Next Steps

### Step 1: Install RMP (if not already installed)

1. Request RMP evaluation from RSI: https://www.roboticsys.com/rmp-evaluation
2. Download and install RMP for Windows
3. Typical installation location: `C:\RSI\10.X.X\`

### Step 2: Configure Python Environment

Add RMP to your Python path in VSCode `settings.json`:

```json
{
    "python.autoComplete.extraPaths": [
        "C:\\RSI\\10.X.X"
    ],
    "python.analysis.extraPaths": [
        "C:\\RSI\\10.X.X"
    ]
}
```

### Step 3: Test RMP Installation

Run the test script to verify everything works:

```powershell
cd d:\Python\ControllerGUI
python test_rmp_installation.py
```

You should see:
```
✓✓✓ ALL TESTS PASSED! ✓✓✓
```

### Step 4: Test RMP with Your GUI (Optional)

To test RMP with your ControllerGUI without modifying your production system:

1. **Edit [controller_config.ini](controller_config.ini)**:
   ```ini
   [Controller]
   type = CommMode4  # Change from DMC-4180 to CommMode4
   ```

2. **Run your GUI**:
   ```powershell
   python ControllerGUI.py
   ```

3. **Access RMP controller**:
   - The controller is available via `comm.rmp`
   - Example: `comm.rmp.get_positions()`

---

## How to Use RMP in Your Code

### Option 1: Direct RMP Access (Testing)

```python
from rmp_controller import RMPController

# Create controller (testing mode - no hardware)
rmp = RMPController(use_hardware=False, num_axes=8)

if rmp.connect():
    rmp.enable_motors()
    
    # Point-to-point motion (like your current Galil code)
    rmp.move_absolute(0, 45.0)  # Move axis A to 45 degrees
    rmp.wait_for_motion_done(0)
    
    position = rmp.get_position(0)
    print(f"Axis A: {position}°")
    
    # PVT streaming (NEW - smooth trajectories)
    waypoints = [
        [0, 0, 0, 0, 0, 0, 0, 0],
        [45, 10, -30, 20, 0, 15, -10, 5],
        [90, 20, -60, 40, 10, 30, -20, 10]
    ]
    
    pvt_data = rmp.generate_pvt_from_waypoints(waypoints, total_time=2.0)
    rmp.stream_pvt_trajectory(pvt_data)
    
    rmp.disable_motors()
    rmp.disconnect()
```

### Option 2: Via Communications Module (Integrated)

```python
from communications import ControllerComm

# Initialize with RMP
rmp_config = {
    'use_hardware': False,
    'num_axes': 8
}

comm = ControllerComm(mode='CommMode4', rmp_config=rmp_config)

# Access RMP controller
comm.rmp.enable_motors()
comm.rmp.move_absolute(0, 45.0)
positions = comm.rmp.get_positions()

comm.close()
```

### Option 3: Via InitializeController (Your Current Pattern)

```python
from InitializeController import InitializeController

# Reads controller_config.ini
ic = InitializeController()

# If type=CommMode4 in INI, comm.rmp is available
if hasattr(ic.comm, 'rmp') and ic.comm.rmp:
    ic.comm.rmp.enable_motors()
    ic.comm.rmp.move_absolute(0, 45.0)
    positions = ic.comm.rmp.get_positions()
```

---

## API Comparison: Galil vs RMP

| Operation | Galil (gclib) | RMP (wrapper) |
|-----------|---------------|---------------|
| Connect | `g.GOpen('192.168.1.100')` | `rmp.connect()` |
| Enable Motors | `g.GCommand('SH')` | `rmp.enable_motors()` |
| Disable Motors | `g.GCommand('MO')` | `rmp.disable_motors()` |
| Move Absolute | `g.GCommand('PA 45')` | `rmp.move_absolute(0, 45.0)` |
| Move Relative | `g.GCommand('PR 10')` | `rmp.move_relative(0, 10.0)` |
| Get Position | `g.GCommand('TP A')` | `rmp.get_position(0)` |
| Get All Positions | `g.GCommand('TP')` | `rmp.get_positions()` |
| Wait for Done | `g.GMotionComplete('A')` | `rmp.wait_for_motion_done(0)` |
| Set Velocity | `g.GCommand('SP 100')` | `rmp.set_velocity(0, 100.0)` |
| **PVT Streaming** | Not available | `rmp.stream_pvt_trajectory(data)` ✨ |

---

## Key Features

### 1. Testing Mode (Phantom Axes)
- No hardware needed
- Tests all motion logic
- Perfect for development

```python
rmp = RMPController(use_hardware=False, num_axes=8)
```

### 2. Point-to-Point Motion
- Maintains your current functionality
- S-curve profiles for smooth motion
- Software limits for safety

### 3. PVT Streaming (NEW!)
- Smooth, blended trajectories
- Multi-axis coordination
- Perfect for complex motion profiles

```python
# Generate from waypoints
pvt_data = rmp.generate_pvt_from_waypoints(waypoints, total_time=2.0)

# Stream to controller
rmp.stream_pvt_trajectory(pvt_data)
```

---

## Configuration Reference

### controller_config.ini Settings

```ini
[Controller]
type = CommMode4  # Use RMP

[CommMode4]
# false = phantom axes (testing), true = real hardware
use_hardware = false
# Number of axes (8 for your system)
num_axes = 8
```

### Axis Configuration

The wrapper reads your existing AXIS_A through AXIS_H sections for:
- Position limits (min/max)
- Speed limits
- Acceleration/deceleration limits
- Gear ratios and scaling

---

## Troubleshooting

### "Cannot import RSI.RapidCode"
- Install RMP from RSI
- Update VSCode settings.json with RMP path
- Verify installation: `python -c "from RSI.RapidCode import *"`

### "RMP controller failed to connect"
- Check if RMP is installed
- Run test_rmp_installation.py for diagnostics
- Check logs in rmp_controller.log

### "Motion not working as expected"
- Verify you're in testing mode (use_hardware=False)
- Check software limits (default ±180°)
- Review rmp_controller.log for errors

---

## Safety Features

The RMP wrapper includes built-in safety:

1. **Software Limits**: ±180° default (configurable)
2. **Abort Function**: Emergency stop all motion
3. **Zero Position**: Set current position as zero
4. **Motion Monitoring**: Check if axes are moving

```python
# Emergency stop
rmp.abort_motion()  # All axes

# Zero current position
rmp.zero_position(0)  # Axis A

# Check if moving
if rmp.is_moving(0):
    print("Axis A is moving")
```

---

## What's Next?

### For Testing (Now):
1. ✅ Run test_rmp_installation.py
2. ✅ Test with phantom axes
3. ✅ Verify motion profiles work

### For Integration (Soon):
1. Modify ControllerGUI.py to support RMP
2. Add GUI toggle between Galil/RMP
3. Test PVT streaming with your data

### For Deployment (Later):
1. Order EtherCAT servos (MyActuator recommended)
2. Set up Raspberry Pi 5 or Linux IPC
3. Deploy to real hardware
4. Test with actual robot

---

## Support

- **Wrapper Code**: See comments in [rmp_controller.py](rmp_controller.py)
- **RMP Documentation**: https://support.roboticsys.com/rmp/
- **Migration Guide**: See [python_hmi_migration_guide.md](d:\Claude\python_hmi_migration_guide.md)
- **Logs**: Check `rmp_controller.log` for detailed debugging

---

## Summary

You now have:
- ✅ Complete RMP integration with your existing architecture
- ✅ Testing capability with phantom axes
- ✅ Backward compatibility with Galil
- ✅ New PVT streaming capability
- ✅ Easy switching between controllers via config file

**Ready to test?** Run:
```powershell
python test_rmp_installation.py
```
