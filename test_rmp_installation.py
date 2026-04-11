"""
================================================================================
                    RMP INSTALLATION TEST SCRIPT
================================================================================

Author: gskovira01
Date: January 13, 2026

PURPOSE:
    Test RMP (RapidCode) installation and verify it works with phantom axes
    Run this BEFORE connecting real hardware to ensure RMP is properly installed

PREREQUISITES:
    1. RMP for Windows installed from RSI (C:\\RSI\\10.X.X\\)
    2. Python path configured to include RMP directory
    3. No hardware connection needed for this test

WHAT THIS TESTS:
    ✓ RMP Python module can be imported
    ✓ Controller object can be created
    ✓ Phantom axes can be configured
    ✓ Basic motion commands work
    ✓ Position queries work
    ✓ Your rmp_controller.py wrapper works

RUN THIS:
    python test_rmp_installation.py

================================================================================
"""

import sys
import traceback
import os
import platform

# Add INtime DLL directory (required for RapidCode)
if platform.system() == "Windows":
    intime_bin = "c:\\Program Files (x86)\\INtime\\bin"
    if os.path.exists(intime_bin):
        os.add_dll_directory(intime_bin)
    
    # Add RMP directory to Python path
    rmp_dir = "C:\\RSI\\10.7.1"
    if os.path.exists(rmp_dir):
        sys.path.append(rmp_dir)

# Try to import RMP at module level
RMP_AVAILABLE = False
MotionController = None

try:
    import RapidCodePython as RapidCode
    MotionController = RapidCode.MotionController
    # Try to get some common classes (may not all exist in every version)
    try:
        RSIMotorType = getattr(RapidCode, 'RSIMotorType', None)
        RSIAction = getattr(RapidCode, 'RSIAction', None)
        RSIAxisSoftwareLimit = getattr(RapidCode, 'RSIAxisSoftwareLimit', None)
        RsiError = getattr(RapidCode, 'RsiError', None)
    except Exception:
        pass
    RMP_AVAILABLE = True
    print(f"RapidCode module imported successfully!")
    print(f"Available attributes: {len(dir(RapidCode))} items")
except ImportError as e:
    RMP_AVAILABLE = False
    print(f"Import error details: {e}")

def test_rsi_import():
    """Test 1: Can we import RSI.RapidCode?"""
    print("\n" + "="*60)
    print("TEST 1: Import RSI.RapidCode Module")
    print("="*60)
    
    if RMP_AVAILABLE:
        print("✓ SUCCESS: RSI.RapidCode imported successfully")
        return True
    else:
        print("✗ FAILED: Could not import RSI.RapidCode")
        print("\n  Troubleshooting:")
        print("  1. Is RMP installed? (Check C:\\RSI\\)")
        print("  2. Is the RMP path in your Python environment?")
        print("  3. In VSCode settings.json, add:")
        print('     "python.autoComplete.extraPaths": ["C:\\\\RSI\\\\10.X.X"]')
        return False

def test_controller_creation():
    """Test 2: Can we create a MotionController?"""
    print("\n" + "="*60)
    print("TEST 2: Create RMP MotionController")
    print("="*60)
    
    if not RMP_AVAILABLE:
        print("✗ SKIPPED: RMP not available")
        return False
    
    try:
        controller = MotionController.CreateFromSoftware()
        
        serial = controller.SerialNumberGet()
        version = controller.FirmwareVersionGet()
        
        print("✓ SUCCESS: MotionController created")
        print(f"  Serial Number: {serial}")
        print(f"  Firmware Version: {version}")
        
        controller.Delete()
        return True
        
    except Exception as e:
        print("✗ FAILED: Could not create MotionController")
        print(f"  Error: {e}")
        traceback.print_exc()
        return False

def test_phantom_axis():
    """Test 3: Can we configure and move a phantom axis?"""
    print("\n" + "="*60)
    print("TEST 3: Phantom Axis Motion Test")
    print("="*60)
    
    if not RMP_AVAILABLE:
        print("✗ SKIPPED: RMP not available")
        return False
    
    try:
        controller = MotionController.CreateFromSoftware()
        
        # Get first axis and configure as phantom
        axis = controller.AxisGet(0)
        axis.MotorTypeSet(RSIMotorType.RSIMotorTypePHANTOM)
        
        print("✓ Phantom axis configured")
        
        # Set user units (91.02 counts per degree)
        axis.UserUnitsSet(91.02)
        
        # Enable and test motion
        axis.AmpEnableSet(True)
        print("✓ Axis enabled")
        
        # Move to 45 degrees
        axis.MoveSCurve(45.0)
        axis.MotionDoneWait()
        
        position = axis.ActualPositionGet()
        print(f"✓ Move complete - Position: {position:.2f}°")
        
        if abs(position - 45.0) < 0.1:
            print("✓ SUCCESS: Phantom axis motion working correctly")
            success = True
        else:
            print(f"✗ WARNING: Expected 45.0°, got {position:.2f}°")
            success = False
        
        axis.AmpEnableSet(False)
        controller.Delete()
        return success
        
    except Exception as e:
        print("✗ FAILED: Phantom axis test failed")
        print(f"  Error: {e}")
        traceback.print_exc()
        return False

def test_rmp_wrapper():
    """Test 4: Does our rmp_controller.py wrapper work?"""
    print("\n" + "="*60)
    print("TEST 4: RMP Controller Wrapper Test")
    print("="*60)
    
    if not RMP_AVAILABLE:
        print("✗ SKIPPED: RMP not available")
        return False
    
    try:
        from rmp_controller import RMPController
        
        # Create controller (testing mode)
        rmp = RMPController(use_hardware=False, num_axes=8)
        
        if not rmp.connect():
            print("✗ FAILED: Could not connect to RMP")
            return False
        
        print("✓ RMP wrapper connected")
        
        # Enable motors
        rmp.enable_motors([0])  # Just test first axis
        print("✓ Motor enabled")
        
        # Test single axis move
        rmp.move_absolute(0, 90.0)
        rmp.wait_for_motion_done(0)
        
        pos = rmp.get_position(0)
        print(f"✓ Single axis move complete - Position: {pos:.2f}°")
        
        # Test multi-axis move
        positions = [10, 20, 30, 40, 50, 60, 70, 80]
        rmp.move_all_axes(positions)
        rmp.wait_for_motion_done()
        
        final_positions = rmp.get_positions()
        print(f"✓ Multi-axis move complete")
        print(f"  Positions: {[f'{p:.1f}' for p in final_positions]}")
        
        # Test PVT streaming
        waypoints = [
            [0, 0, 0, 0, 0, 0, 0, 0],
            [45, 45, 45, 45, 45, 45, 45, 45],
            [90, 90, 90, 90, 90, 90, 90, 90]
        ]
        
        pvt_data = rmp.generate_pvt_from_waypoints(waypoints, total_time=1.0)
        rmp.stream_pvt_trajectory(pvt_data)
        
        print("✓ PVT streaming test complete")
        
        rmp.disable_motors()
        rmp.disconnect()
        
        print("✓ SUCCESS: RMP wrapper working correctly")
        return True
        
    except Exception as e:
        print("✗ FAILED: RMP wrapper test failed")
        print(f"  Error: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  RMP (RapidCode) INSTALLATION TEST SUITE".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    results = []
    
    # Test 1: Import
    results.append(("RSI.RapidCode Import", test_rsi_import()))
    
    # Only continue if import succeeded
    if results[0][1]:
        # Test 2: Controller creation
        results.append(("Controller Creation", test_controller_creation()))
        
        # Test 3: Phantom axis
        results.append(("Phantom Axis Motion", test_phantom_axis()))
        
        # Test 4: Wrapper class
        results.append(("RMP Wrapper Class", test_rmp_wrapper()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n✓✓✓ ALL TESTS PASSED! ✓✓✓")
        print("\nYour RMP installation is working correctly.")
        print("You can now:")
        print("  1. Update controller_config.ini to add CommMode4")
        print("  2. Integrate RMP with your ControllerGUI")
        print("  3. Test with phantom axes before connecting hardware")
        print("\n")
        return 0
    else:
        print("\n✗✗✗ SOME TESTS FAILED ✗✗✗")
        print("\nPlease fix the issues above before proceeding.")
        print("\nCommon issues:")
        print("  - RMP not installed: Download from RSI")
        print("  - Python path not configured: Update VSCode settings.json")
        print("  - Wrong Python version: RMP requires Python 3.8+")
        print("\n")
        return 1

if __name__ == "__main__":
    exit_code = main()
    
    print("\nPress Enter to exit...")
    input()
    
    sys.exit(exit_code)
