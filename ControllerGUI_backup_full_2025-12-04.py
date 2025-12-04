"""
================================================================================
                        CONTROLLER GUI SYSTEM
================================================================================

Author: gskovira01
Last Updated: December 4, 2025
Version: 1.1.0

PURPOSE:
    Touchscreen-friendly GUI for 8-axis controller interface with modular numeric keypad popup.
    Supports Galil and ClearCore controllers. Features tabbed interface, dynamic command mapping,
    periodic status polling, indicator lights, and robust error handling.

KEY FEATURES:
    - Tabbed interface for 8 servos (A-H)
    - Modular numeric keypad popup for value entry (see numeric_keypad.py)
    - Min/max validation for all numeric fields
    - Dynamic command mapping for Galil and ClearCore controllers
    - Periodic status polling and indicator lights for each servo
    - Debug log window for sent/received commands and errors
    - Zero Position button for each axis
    - Improved error handling and user feedback

MAIN FUNCTIONS:
    get_controller_type_from_ini(ini_path):
        Reads the controller type from the INI file.

    build_servo_tab(servo_num):
        Builds the tab layout for a single servo, including status indicator, value fields, and control buttons.

    poll_and_update_indicator(axis_index):
        Polls the controller for the enable/disable status of the given axis and updates the indicator and status text.

    handle_servo_event(event, values):
        Handles all servo-related button events (enable, disable, jog, set values).

    poll_active_servo_indicator(window, comm, values=None):
        Polls the currently active servo tab and updates its indicator.

    show_numeric_keypad(...):
        Numeric keypad popup for value entry (now in numeric_keypad.py).

================================================================================
"""

# ...existing code...
