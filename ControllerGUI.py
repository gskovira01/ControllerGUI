# Utility: display ints without decimals, otherwise round to 1 decimal place
def format_display_value(val):
    try:
        fval = round(float(val), 1)
        if fval.is_integer():
            return str(int(fval))
        return f"{fval:.1f}"
    except Exception:
        return str(val)
"""
================================================================================
                        CONTROLLER GUI SYSTEM
================================================================================

Author: gskovira01
Last Updated: December 14, 2025
Version: 1.2.0

PURPOSE:
    Touchscreen-friendly GUI for an 8-axis Galil controller interface with modular numeric keypad popup.
    Features tabbed interface, dynamic command mapping, modular background polling,
    indicator lights, and robust error handling.

KEY FEATURES:
    - Tabbed interface for 8 servos (A-H)
    - Modular numeric keypad popup for value entry (see numeric_keypad.py)
    - Min/max validation for all numeric fields
    - Dynamic command mapping for Galil controller
    - Modular background polling (see ControllerPolling.py):
        * Runs as a background thread
        * Periodically polls actual position, torque, and enable/disable status for each servo
        * Communicates results to GUI via thread-safe events
    - Indicator lights and status for each servo
    - Debug log window for sent/received commands and errors
    - Zero Position button for each axis
    - Improved error handling and user feedback

FUNCTIONS DEFINED IN THIS FILE:
    get_controller_type_from_ini(ini_path='controller_config.ini')
        - Reads the controller type from the INI configuration file.

    build_servo_tab(servo_num)
        - Builds and returns the GUI layout for a single servo tab.

    handle_servo_event(event, values)
        - Handles all servo-related button events (enable, disable, jog, set values, etc.).

    (Polling logic moved to ControllerPolling.py)
        - See ControllerPolling.start_polling_thread(window, comm):
            * Starts a background thread that polls actual position, torque, and enable/disable status for each servo and updates the GUI.

================================================================================
"""

# ============================================================================
# Imports and Configuration
# ============================================================================

# ============================================================================
# Imports and Configuration
# ============================================================================
import FreeSimpleGUI as sg
import threading  # For future use if needed
import platform                            # Cross-platform OS detection and adaptation
import configparser
import os
from communications import ControllerComm
from numeric_keypad import NumericKeypad

# ============================================================================
# Constants and Global Variables
# =====================
# Axis scaling and units dictionary
# =====================
# Example: { 'A': {'pulses': 20000, 'degrees': 360, 'scaling': 20000/360}, ... }
# Read axis parameters from controller_config.ini
import configparser
AXIS_UNITS = {}
axis_ini = configparser.ConfigParser()
axis_ini.read(os.path.join(os.path.dirname(__file__), 'controller_config.ini'))
for axis in 'ABCDEFGH':
    section = f'AXIS_{axis}'
    if section in axis_ini:
        AXIS_UNITS[axis] = {
            'min': float(axis_ini[section]['min']),
            'max': float(axis_ini[section]['max']),
            'pulses': float(axis_ini[section]['pulses']),
            'degrees': float(axis_ini[section]['degrees']),
            'scaling': float(axis_ini[section]['scaling']),
            'gearbox': float(axis_ini[section]['gearbox'])
        }
# ============================================================================


# ============================================================================
#                         PLATFORM DETECTION & CONFIGURATION
# ============================================================================

# Cross-platform compatibility flags
IS_WINDOWS = platform.system() == "Windows"      # Windows development environment
IS_RASPBERRY_PI = platform.system() == "Linux" and platform.machine().startswith('arm')  # Pi deployment

GLOBAL_FONT = ('Courier New', 10)
POSITION_LABEL_FONT = ('Courier New', 10, 'bold')
CLEAR_BUTTON_FONT = ('Courier New', 9)
LOG_POSITION_POLLS = False  # Toggle to suppress noisy MG _RP logs in the GUI
DEFAULT_INPUT_BG = '#FFFFFF'
HIGHLIGHT_INPUT_BG = '#CCFFCC'
PENDING_INPUT_BG = '#FFFACD'


def pulses_to_degrees(raw_val, axis_letter):
    """Convert controller pulses to degrees using scaling and gearbox."""
    try:
        axis_units = AXIS_UNITS.get(axis_letter, {})
        scaling = axis_units.get('scaling', 1) or 1
        gearbox = axis_units.get('gearbox', 1) or 1
        return float(raw_val) / (scaling * gearbox)
    except Exception:
        return None


def bind_jog_press_release(window):
    """Bind mouse press/release for jog CW/CCW buttons to synthesize events."""
    for i in range(1, 9):
        for direction in ['cw', 'ccw']:
            key = f'S{i}_jog_{direction}'
            if key in window.AllKeysDict:
                btn = window[key]
                try:
                    btn.Widget.bind('<ButtonPress-1>', lambda e, s=i, d=direction: window.write_event_value('JOG_PRESS', (s, d, True)))
                    btn.Widget.bind('<ButtonRelease-1>', lambda e, s=i, d=direction: window.write_event_value('JOG_PRESS', (s, d, False)))
                except Exception:
                    pass


def set_pending_highlight(window, servo_num, field):
    """Set field background to yellow if current value differs from last confirmed setpoint."""
    try:
        key = f'S{servo_num}_{field}'
        current = window[key].get()
        if not current or current in ('-', '.'):  # nothing meaningful
            window[key].update(background_color=DEFAULT_INPUT_BG)
            return False
        if not hasattr(window, '_last_setpoints') or not window._last_setpoints:
            window[key].update(background_color=PENDING_INPUT_BG)
            return True
        last_val = window._last_setpoints[servo_num - 1].get(field)
        try:
            current_val = float(current)
            pending = (last_val is None) or abs(current_val - float(last_val)) > 1e-6
        except Exception:
            pending = True
        window[key].update(background_color=PENDING_INPUT_BG if pending else DEFAULT_INPUT_BG)
        return pending
    except Exception:
        return False
# -----------------------------
# Servo setup:Dictionary mapping each field to its min and max values (same for all servos)
# Automatically generate command mappings for all 8 servos
# The min an max fields for each servo is derived from AXIS_UNITS which are defined in the controller_config.ini file.
# -----------------------------
# Command Mapping Dictionaries
# -----------------------------
# GALIL_COMMAND_MAP: Maps GUI actions to Galil controller commands (A-H axes)
GALIL_COMMAND_MAP = {}
AXIS_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
for i in range(1, 9):
    axis_letter = AXIS_LETTERS[i-1]
    GALIL_COMMAND_MAP[f'S{i}_enable'] = f'SH{axis_letter}'
    GALIL_COMMAND_MAP[f'S{i}_disable'] = f'MO{axis_letter}'
    GALIL_COMMAND_MAP[f'S{i}_start'] = f'BG{axis_letter}'
    GALIL_COMMAND_MAP[f'S{i}_stop'] = f'ST{axis_letter}'
    GALIL_COMMAND_MAP[f'S{i}_jog'] = (lambda speed, axis=axis_letter: f'JG{axis}={speed};BG{axis}')
    GALIL_COMMAND_MAP[f'S{i}_speed'] = (lambda value, axis=axis_letter: f'SP{axis}={value}')
    GALIL_COMMAND_MAP[f'S{i}_accel'] = (lambda value, axis=axis_letter: f'AC{axis}={value}')
    GALIL_COMMAND_MAP[f'S{i}_decel'] = (lambda value, axis=axis_letter: f'DC{axis}={value}')
    GALIL_COMMAND_MAP[f'S{i}_abs_pos'] = (lambda value, axis=axis_letter: f'PA{axis}={value}')
    GALIL_COMMAND_MAP[f'S{i}_rel_pos'] = (lambda value, axis=axis_letter: f'PR{axis}={value}')

# Galil only
COMMAND_MAP = GALIL_COMMAND_MAP

# Initialize ControllerComm with Galil config from INI file
comm = None
try:
    config = configparser.ConfigParser()
    config.read('controller_config.ini')
    galil_config = dict(config.items('CommMode1')) if config.has_section('CommMode1') else {}
    comm = ControllerComm(mode='CommMode1', galil_config=galil_config)
    print(f'[DEBUG] ControllerComm initialized: comm={comm}, mode={getattr(comm, "mode", None)}')
except Exception as comm_error:
    comm = None
    import traceback
    error_details = f'{comm_error}\n' + traceback.format_exc()
    sg.popup_error(f'Failed to initialize controller communications:\n{comm_error}', keep_on_top=True)
    print(f'[ERROR] Failed to initialize controller communications: {error_details}')

def build_servo_tab(servo_num):
###############################################################################
    """
    Build the tab layout for a single servo.
    Includes status indicator, value fields, and control buttons.
    Args:
        servo_num (int): Servo number (1-8)
    Returns:
        List: PySimpleGUI layout for the tab
    """
    layout = [
        [sg.Text(f'Servo {servo_num}', font=POSITION_LABEL_FONT),
         sg.Text('●', key=f'S{servo_num}_status_light', font=('Courier New', 16), text_color='gray'),
         sg.Text('Disabled', key=f'S{servo_num}_status_text', font=GLOBAL_FONT, text_color='gray')],
        [sg.Button('Clear Faults', key=f'S{servo_num}_clear_faults', size=(14,2), font=GLOBAL_FONT)],
        [sg.Text('Speed:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_speed', size=(10,1), font=GLOBAL_FONT, enable_events=True),
            sg.Text('DPS ', font=GLOBAL_FONT),
         sg.Button('⌨', key=f'S{servo_num}_speed_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_speed_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Acceleration:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_accel', size=(10,1), font=GLOBAL_FONT, enable_events=True),
            sg.Text('DPS²', font=GLOBAL_FONT),
         sg.Button('⌨', key=f'S{servo_num}_accel_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_accel_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Deceleration:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_decel', size=(10,1), font=GLOBAL_FONT, enable_events=True),
            sg.Text('DPS²', font=GLOBAL_FONT),
         sg.Button('⌨', key=f'S{servo_num}_decel_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_decel_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Absolute Position (DEG):', size=(18,1), font=GLOBAL_FONT),
            sg.Input(key=f'S{servo_num}_abs_pos', size=(10,1), font=GLOBAL_FONT, enable_events=True),
                sg.Text('DEG ', font=GLOBAL_FONT),
            sg.Button('⌨', key=f'S{servo_num}_abs_pos_keypad', size=(2,1), font=GLOBAL_FONT),
            sg.Button('OK', key=f'S{servo_num}_abs_pos_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Relative Position (DEG):', size=(18,1), font=GLOBAL_FONT),
            sg.Input(key=f'S{servo_num}_rel_pos', size=(10,1), font=GLOBAL_FONT, enable_events=True),
                sg.Text('DEG ', font=GLOBAL_FONT),
            sg.Button('⌨', key=f'S{servo_num}_rel_pos_keypad', size=(2,1), font=GLOBAL_FONT),
            sg.Button('OK', key=f'S{servo_num}_rel_pos_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Actual Position:', size=(18,1), font=GLOBAL_FONT), sg.Text('0', key=f'S{servo_num}_actual_pos', size=(10,1), font=GLOBAL_FONT), sg.Text('DEG', font=GLOBAL_FONT)],
        [sg.Text('Actual Position:', size=(18,1), font=GLOBAL_FONT), sg.Text('0', key=f'S{servo_num}_actual_pos_pulses', size=(10,1), font=GLOBAL_FONT), sg.Text('PUL', font=GLOBAL_FONT)],
        [
            sg.Button('Servo Enable', key=f'S{servo_num}_enable', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Servo Disable', key=f'S{servo_num}_disable', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Zero Position', key=f'S{servo_num}_zero_pos', size=(12,2), font=GLOBAL_FONT)  # Default color (same as Jog)
        ],
        [
            sg.Button('Start Motion', key=f'S{servo_num}_start', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Stop Motion', key=f'S{servo_num}_stop', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Jog CW', key=f'S{servo_num}_jog_cw', size=(8,2), font=GLOBAL_FONT),
            sg.Button('Jog CCW', key=f'S{servo_num}_jog_ccw', size=(8,2), font=GLOBAL_FONT)
        ]
    ]
    return layout



# Create a tab for each servo (1-8)
# -----------------------------
# Build tab group for all servos
# -----------------------------
servo_tabs = [sg.Tab(f'Servo {i}', build_servo_tab(i), key=f'TAB{i}') for i in range(1, 9)]



# List of all numeric input keys and keypad button keys for all servos
# -----------------------------
# Build lists of input keys and keypad button keys for all servos
# -----------------------------

# Default numeric limits for fields (used if not found in AXIS_UNITS)
NUMERIC_LIMITS = {
    'speed': (-180, 180),
    'accel': (0, 180),
    'decel': (0, 180),
    'abs_pos': (0, 180),
    'rel_pos': (-90, 90),
}

# -----------------------------
# Main window layout
# -----------------------------
NUMERIC_INPUT_KEYS = []
NUMERIC_KEYPAD_BUTTONS = []
for i in range(1, 9):
    for field in ['speed', 'accel', 'decel', 'abs_pos', 'rel_pos']:
        NUMERIC_INPUT_KEYS.append(f'S{i}_{field}')
        NUMERIC_KEYPAD_BUTTONS.append(f'S{i}_{field}_keypad')

###############################################################################
# GUI Layout
###############################################################################
# Make DEBUG_LOG Multiline write-only so updates render but user can't edit
layout = [
    [
        sg.TabGroup([servo_tabs], key='TABGROUP', enable_events=True),
        sg.Push(),
        sg.Checkbox('Show Poll Logs', key='SHOW_POLL_LOGS', enable_events=True, default=False, font=GLOBAL_FONT),
        sg.Button('Shutdown', key='SHUTDOWN', size=(8,1), button_color=('white', 'red'), font=GLOBAL_FONT)
    ],
    [sg.Multiline('', key='DEBUG_LOG', size=(80, 8), font=('Courier New', 9), autoscroll=True, disabled=False, write_only=True, text_color='black', border_width=0)],
]

window = sg.Window("Controller GUI", layout, size=(700, 480), font=GLOBAL_FONT, finalize=True, return_keyboard_events=True)

###############################################################################
# Show popup if communications not initialized
###############################################################################
if comm is None:
    sg.popup_error('Controller communications not initialized. Check INI file and hardware connection.', keep_on_top=True)

window_closed = False
import time
# Import the polling thread from ControllerPolling
from ControllerPolling import start_polling_thread

def initialize_setpoints_from_controller(window, comm):
    """Query controller for current setpoints/status and seed GUI fields."""
    if not comm:
        return
    try:
        mode = getattr(comm, 'mode', None)
    except Exception:
        mode = None
    # Currently only implemented for Galil (CommMode1) where MG operands are available
    if mode != 'CommMode1':
        return
    for idx, axis_letter in enumerate(AXIS_LETTERS):
        servo_num = idx + 1
        scaling = AXIS_UNITS.get(axis_letter, {}).get('scaling', 1) or 1
        gearbox = AXIS_UNITS.get(axis_letter, {}).get('gearbox', 1) or 1
        denom = scaling * gearbox if scaling * gearbox != 0 else 1
        queries = {
            'speed': f'MG _SP{axis_letter}',
            'accel': f'MG _AC{axis_letter}',
            'decel': f'MG _DC{axis_letter}',
            'abs_pos': f'MG _TP{axis_letter}',
            'status': f'MG _MO{axis_letter}',
        }
        results = {}
        for field, cmd in queries.items():
            try:
                resp = comm.send_command(cmd)
                if isinstance(resp, str):
                    # Take the first numeric token
                    for line in resp.splitlines():
                        line = line.strip()
                        try:
                            results[field] = float(line)
                            break
                        except ValueError:
                            continue
            except Exception:
                continue
        # Update numeric fields (convert pulses to degrees)
        for field in ['speed', 'accel', 'decel', 'abs_pos']:
            if field not in results:
                continue
            raw = results[field]
            val_deg = raw / denom if field in ['speed', 'accel', 'decel', 'abs_pos'] else raw
            formatted = format_display_value(val_deg)
            window[f'S{servo_num}_{field}'].update(formatted)
            # Track last setpoints for cancel restore
            if not hasattr(window, '_last_setpoints'):
                window._last_setpoints = [{f: None for f in ['speed', 'accel', 'decel', 'abs_pos', 'rel_pos']} for _ in range(8)]
            window._last_setpoints[servo_num - 1][field] = val_deg
        # Relative position has no direct query; reset to 0
        window[f'S{servo_num}_rel_pos'].update('0')
        window._last_setpoints[servo_num - 1]['rel_pos'] = 0
        # Update enable/disable indicator using status (Galil _MO returns 0 when disabled)
        status_val = results.get('status')
        if status_val is not None:
            enabled = status_val == 0
            if enabled:
                window[f'S{servo_num}_status_light'].update('●', text_color='#00FF00')
                window[f'S{servo_num}_status_text'].update('Enabled', text_color='#00FF00')
            else:
                window[f'S{servo_num}_status_light'].update('●', text_color='#FFFF00')
                window[f'S{servo_num}_status_text'].update('Disabled', text_color='#FFFF00')
        if not window_closed:
            window['DEBUG_LOG'].print(f'[INIT] S{servo_num} seeded from controller: {results}')


def update_setpoint_highlight(window, servo_num, actual_deg=None, tolerance=0.1):
    """Highlight abs_pos: yellow if pending, green if on target, otherwise white."""
    key = f'S{servo_num}_abs_pos'
    pending = set_pending_highlight(window, servo_num, 'abs_pos')
    if pending:
        return
    try:
        target_str = window[key].get()
        if not target_str or target_str in ('-', '.'):
            window[key].update(background_color=DEFAULT_INPUT_BG)
            return
        if actual_deg is None:
            try:
                actual_deg = float(window._last_valid_pos[servo_num - 1]) if window._last_valid_pos[servo_num - 1] else None
            except Exception:
                actual_deg = None
        if actual_deg is None:
            window[key].update(background_color=DEFAULT_INPUT_BG)
            return
        target = float(target_str)
        if abs(actual_deg - target) <= tolerance:
            window[key].update(background_color=HIGHLIGHT_INPUT_BG)
        else:
            window[key].update(background_color=DEFAULT_INPUT_BG)
    except Exception:
        window[key].update(background_color=DEFAULT_INPUT_BG)


# Bind jog press/release after window creation
bind_jog_press_release(window)

# Seed GUI setpoints/status from controller before starting polling
initialize_setpoints_from_controller(window, comm)


# --- Define handle_servo_event before main event loop ---
def handle_servo_event(event, values):
    # Parse servo number from event string (e.g., 'S3_enable' -> 3)
    if isinstance(event, str) and event.startswith('S') and '_' in event:
        try:
            servo_num_str, action = event[1:].split('_', 1)
            servo_num = int(servo_num_str)
            axis_letter = AXIS_LETTERS[servo_num - 1]
            map_key = f'S{servo_num}_{action}'
            print(f'[DEBUG] handle_servo_event: event={event}, servo_num={servo_num}, action={action}')
        except Exception:
            print(f'[DEBUG] handle_servo_event: failed to parse event={event}')
            return

        # Always check for setpoint OK button, regardless of map_key in COMMAND_MAP
        setpoint_fields = ['speed', 'accel', 'decel', 'abs_pos', 'rel_pos']
        if not hasattr(window, '_last_setpoints'):
            window._last_setpoints = [{f: None for f in setpoint_fields} for _ in range(8)]
        for field in setpoint_fields:
            print(f'[DEBUG] Comparing action={action} to {field}_ok')
            if action == f'{field}_ok':
                print(f'[DEBUG] handle_servo_event called for {field}_ok, S{servo_num}')
                original_text = window[f'S{servo_num}_{field}'].get()
                previous_setpoint = window._last_setpoints[servo_num - 1].get(field)
                value = values.get(f'S{servo_num}_{field}', None)
                if value is None or value == '':
                    print(f'[DEBUG] No value entered for {field} (S{servo_num})')
                    sg.popup_error(f'Please enter a value for {field}', keep_on_top=True)
                    print('[DEBUG] RETURN: No value entered')
                    return
                try:
                    # Accept float input and keep one decimal place for display
                    value = round(float(value), 1)
                    formatted_value = format_display_value(value)
                    window[f'S{servo_num}_{field}'].update(formatted_value)
                except ValueError:
                    print(f'[DEBUG] Invalid value for {field} (S{servo_num}): {value}')
                    sg.popup_error(f'Invalid value for {field}', keep_on_top=True)
                    print('[DEBUG] RETURN: Invalid value')
                    return
                axis_letter = AXIS_LETTERS[servo_num - 1]
                if axis_letter in AXIS_UNITS and field in AXIS_UNITS[axis_letter]:
                    min_val = AXIS_UNITS[axis_letter]['min']
                    max_val = AXIS_UNITS[axis_letter]['max']
                else:
                    min_val, max_val = NUMERIC_LIMITS.get(field, (0, 54000))
                # For relative moves, ensure resulting position stays within limits
                if field == 'rel_pos':
                    try:
                        current_pos = float(window._last_valid_pos[servo_num - 1]) if window._last_valid_pos[servo_num - 1] else 0.0
                    except Exception:
                        current_pos = 0.0
                    target_pos = current_pos + value
                    if target_pos < min_val or target_pos > max_val:
                        print(f'[DEBUG] Relative move would exceed limits: current={current_pos}, delta={value}, target={target_pos}, limits=({min_val},{max_val})')
                        sg.popup_error(f"Move would exceed limits ({min_val} to {max_val}). Current: {current_pos}, Target: {target_pos}", keep_on_top=True)
                        return
                if value < min_val or value > max_val:
                    print(f'[DEBUG] Value for {field} (S{servo_num}) out of range: {value}')
                    sg.popup_error(f"Value for {field} must be between {min_val} and {max_val}", keep_on_top=True)
                    print('[DEBUG] RETURN: Value out of range')
                    return
                # Confirm with user before sending command
                confirm_label = field.replace('_', ' ').title()
                confirm = sg.popup_ok_cancel(
                    f"Send setpoint for {confirm_label} (S{servo_num})?\nValue: {formatted_value}",
                    keep_on_top=True,
                    title='Confirm Setpoint'
                )
                if confirm != 'OK':
                    restore_val = previous_setpoint if previous_setpoint is not None else original_text
                    window[f'S{servo_num}_{field}'].update(format_display_value(restore_val) if restore_val not in (None, '') else '')
                    if not window_closed:
                        window['DEBUG_LOG'].print(f"[INFO] Setpoint canceled for {confirm_label} S{servo_num}; reverted to {format_display_value(restore_val) if restore_val not in (None, '') else 'blank'}\n", end='')
                        window['DEBUG_LOG'].Widget.see('end')
                        if field == 'abs_pos':
                            update_setpoint_highlight(window, servo_num)
                        else:
                            set_pending_highlight(window, servo_num, field)
                    print('[DEBUG] User canceled setpoint send')
                    return
                # Convert degrees to pulses using scaling and gearbox
                scaling = AXIS_UNITS[axis_letter].get('scaling', 1)
                gearbox = AXIS_UNITS[axis_letter].get('gearbox', 1)
                pulses_value = int(round(value * scaling * gearbox))

                cmd_func = COMMAND_MAP.get(f'S{servo_num}_{field}')
                if callable(cmd_func):
                    cmd = cmd_func(pulses_value)
                else:
                    cmd = cmd_func
                print(f'[DEBUG] About to send setpoint command: {cmd}')
                if not cmd:
                    print('[DEBUG] RETURN: cmd is None')
                    return
                if not comm:
                    print('[DEBUG] RETURN: comm is None')
                    sg.popup_error('Controller communications not initialized.', keep_on_top=True)
                    return
                try:
                    response = comm.send_command(cmd)
                    print(f'[DEBUG] Setpoint command sent, response: {response}')
                    if not window_closed:
                        log_line = f"[TEST LOG] {field.capitalize()} OK for S{servo_num}: Sent {cmd}\nReply: {response}\n"
                        print(f'[DEBUG] Logging setpoint to DEBUG_LOG: {log_line.strip()}')
                        window['DEBUG_LOG'].print(log_line, end='')
                        window['DEBUG_LOG'].Widget.see('end')
                        window.refresh()
                    # Persist last confirmed setpoint value for cancel restores
                    window._last_setpoints[servo_num - 1][field] = value
                    if field == 'abs_pos':
                        update_setpoint_highlight(window, servo_num)
                    else:
                        set_pending_highlight(window, servo_num, field)
                except Exception as e:
                    import traceback
                    error_details = f'{e}\n' + traceback.format_exc()
                    print(f'[DEBUG] Exception sending setpoint command: {error_details}')
                    sg.popup_error(f'Error sending command: {e}', keep_on_top=True)
                    if not window_closed:
                        window['DEBUG_LOG'].update(f'[ERROR] Error sending command: {error_details}\n', append=True)
                        window['DEBUG_LOG'].Widget.see('end')
                return
        # Only handle direct motor control buttons if not a setpoint OK event
        if map_key in COMMAND_MAP:
            cmd = None
            match action:
                case 'jog':
                    speed_val = values.get(f'S{servo_num}_speed', None)
                    if speed_val is None or speed_val == '':
                        sg.popup_error('Please enter a speed value for Jog', keep_on_top=True)
                        return
                    try:
                        speed_val = float(speed_val)
                    except ValueError:
                        sg.popup_error('Invalid speed value for Jog', keep_on_top=True)
                        return
                    # Soft limit: prevent jogging past min/max if current position known
                    axis_letter = AXIS_LETTERS[servo_num - 1]
                    try:
                        current_pos = float(window._last_valid_pos[servo_num - 1]) if window._last_valid_pos[servo_num - 1] else None
                    except Exception:
                        current_pos = None
                    min_val, max_val = AXIS_UNITS[axis_letter]['min'], AXIS_UNITS[axis_letter]['max']
                    if current_pos is not None:
                        if speed_val > 0 and current_pos >= max_val:
                            sg.popup_error(f'Jog blocked: at limit {max_val} deg', keep_on_top=True)
                            return
                        # Allow jogging below min but cap speed to 20% of max speed
                        if speed_val < 0 and current_pos <= min_val:
                            max_speed_limit = NUMERIC_LIMITS.get('speed', (0, 180))[1]
                            capped = -min(abs(speed_val), max_speed_limit * 0.1)
                            speed_val = capped
                    # Convert degrees/sec to pulses/sec using scaling and gearbox
                    axis_letter = AXIS_LETTERS[servo_num - 1]
                    scaling = AXIS_UNITS[axis_letter].get('scaling', 1)
                    gearbox = AXIS_UNITS[axis_letter].get('gearbox', 1)
                    speed_val = int(round(speed_val * scaling * gearbox))
                    cmd_func = COMMAND_MAP[map_key]
                    if callable(cmd_func):
                        cmd = cmd_func(speed_val)
                    else:
                        cmd = cmd_func
                case 'enable' | 'disable' | 'start' | 'stop':
                    cmd = COMMAND_MAP[map_key] if not callable(COMMAND_MAP[map_key]) else None
                case _:
                    # For any other actions, fallback to original logic if needed
                    cmd = COMMAND_MAP[map_key] if not callable(COMMAND_MAP[map_key]) else None
            if cmd:
                if comm:
                    try:
                        # If disabling, send stop command first
                        if action == 'disable':
                            stop_key = f'S{servo_num}_stop'
                            stop_cmd = COMMAND_MAP.get(stop_key)
                            if stop_cmd:
                                stop_cmd_val = stop_cmd if not callable(stop_cmd) else stop_cmd()
                                comm.send_command(stop_cmd_val)
                        response = comm.send_command(cmd)
                        # Log request and reply in DEBUG_LOG for all actions
                        if not window_closed:
                            prev_log = window['DEBUG_LOG'].get()
                            new_log = f"[TEST LOG] {action.capitalize()} button clicked for S{servo_num}: Sent {cmd}\nReply: {response}\n"
                            window['DEBUG_LOG'].update(prev_log + new_log)
                        # Immediately update indicator color (bright green for enable, bright yellow for disable)
                        match action:
                            case 'enable':
                                window[f'S{servo_num}_status_light'].update('●', text_color='#00FF00')  # Bright green
                                window[f'S{servo_num}_status_text'].update('Enabled', text_color='#00FF00')
                            case 'disable':
                                window[f'S{servo_num}_status_light'].update('●', text_color='#FFFF00')  # Bright yellow
                                window[f'S{servo_num}_status_text'].update('Disabled', text_color='#FFFF00')
                    except Exception as e:
                        import traceback
                        error_details = f'{e}\n' + traceback.format_exc()
                        sg.popup_error(f'Error sending command: {e}', keep_on_top=True)
                        if not window_closed:
                            prev_log = window['DEBUG_LOG'].get()
                            window['DEBUG_LOG'].update(prev_log + f'[ERROR] Error sending command: {error_details}\n')
                else:
                    sg.popup_error('Controller communications not initialized.', keep_on_top=True)
            return


def handle_jog_press(window, comm, servo_num, direction, is_press, values):
    """Start jog on press and stop on release for Jog CW/CCW buttons."""
    if comm is None:
        print('[DEBUG] No comm object; cannot jog')
        return
    try:
        axis_letter = AXIS_LETTERS[servo_num - 1]
    except Exception:
        print(f'[DEBUG] Invalid servo_num for jog: {servo_num}')
        return

    speed_str = values.get(f'S{servo_num}_speed', '')
    if speed_str in ('', '-', '.'):
        print('[DEBUG] No speed set; ignoring jog press')
        return
    try:
        speed_val = float(speed_str)
    except ValueError:
        print(f'[DEBUG] Invalid speed value for Jog: {speed_str}')
        return

    sign = 1 if str(direction).lower() == 'cw' else -1
    signed_speed = speed_val * sign

    axis_units = AXIS_UNITS.get(axis_letter, {})
    scaling = axis_units.get('scaling', 1) or 1
    gearbox = axis_units.get('gearbox', 1) or 1
    min_val = axis_units.get('min', NUMERIC_LIMITS['abs_pos'][0])
    max_val = axis_units.get('max', NUMERIC_LIMITS['abs_pos'][1])

    try:
        current_pos = float(window._last_valid_pos[servo_num - 1]) if window._last_valid_pos[servo_num - 1] else None
    except Exception:
        current_pos = None

    if current_pos is not None:
        if signed_speed > 0 and current_pos >= max_val:
            sg.popup_error(f'Jog blocked: at upper limit {max_val} deg', keep_on_top=True)
            return
        if signed_speed < 0 and current_pos <= min_val:
            # Allow slow creep back into range
            max_speed_limit = NUMERIC_LIMITS.get('speed', (0, 180))[1]
            signed_speed = -min(abs(signed_speed), max_speed_limit * 0.1)

    pulses_speed = int(round(signed_speed * scaling * gearbox))

    if is_press:
        cmd = f'JG{axis_letter}={pulses_speed};BG{axis_letter}'
        try:
            response = comm.send_command(cmd)
            print(f'[DEBUG] JOG press command: {cmd} -> {response}')
        except Exception as ex:
            print(f'[DEBUG] Jog press failed: {ex}')
    else:
        cmd = f'ST{axis_letter}'
        try:
            response = comm.send_command(cmd)
            print(f'[DEBUG] JOG release command: {cmd} -> {response}')
        except Exception as ex:
            print(f'[DEBUG] Jog release failed: {ex}')

# Start the background polling thread using ControllerPolling
# This line starts the background polling thread for the GUI. Specifically:
# start_polling_thread(window, comm) is a function (imported from ControllerPolling.py) that launches a separate thread.
# This thread periodically polls the controller (using the comm object) for status updates (like position, torque, enable/disable state) for each servo.
# It sends these updates back to the GUI window using thread-safe events (such as POSITION_POLL).

polling_thread, polling_stop_event = start_polling_thread(window, comm)

# Main event loop (no periodic polling here)
while True:
    event, values = window.read(timeout=100)
    if event == 'SHOW_POLL_LOGS':
        LOG_POSITION_POLLS = bool(values.get('SHOW_POLL_LOGS', False))
        continue
    # Ensure counters are initialized before use
    if not hasattr(window, '_invalid_resp_counters'):
        window._invalid_resp_counters = [0]*8
    if not hasattr(window, '_last_valid_pos'):
        window._last_valid_pos = ['']*8
    if not hasattr(window, '_limit_tripped'):
        window._limit_tripped = [False]*8

    if event == 'JOG_PRESS':
        try:
            servo_num, direction, is_press = values.get(event, (None, None, None))
        except Exception:
            servo_num, direction, is_press = None, None, None
        if servo_num is not None and direction is not None and is_press is not None:
            handle_jog_press(window, comm, int(servo_num), direction, bool(is_press), values)
        else:
            print(f'[DEBUG] Invalid JOG_PRESS payload: {values.get(event)}')
        continue
    if event == sg.WIN_CLOSED:
        window_closed = True
        break

    if event == 'POSITION_POLL':
        # Handle position update from background thread
        data = values[event] if event in values else None
        if data:
            i = data['servo']
            axis_letter = data['axis_letter']
            pos_resp = data.get('pos_resp')
            raw_resp = data.get('raw_resp')
            pos_val = None
            pos_val_deg = None
            valid = False
            # Log the raw response for debugging (optional)
            if not window_closed and LOG_POSITION_POLLS:
                window['DEBUG_LOG'].print(f'Axis {axis_letter}: MG _RP{axis_letter} raw response: {raw_resp}')
            if pos_resp is not None and str(pos_resp).strip() != ':' and str(pos_resp).strip() != '':
                try:
                    pos_val_pulses = float(pos_resp)
                    axis_units = AXIS_UNITS[axis_letter]
                    pulses_per_degree = axis_units.get('scaling') or (axis_units.get('pulses', 0) / max(axis_units.get('degrees', 1), 1e-9))
                    if pulses_per_degree <= 0:
                        pulses_per_degree = 1
                    gearbox = axis_units.get('gearbox', 1)
                    pos_val_deg = pos_val_pulses / (pulses_per_degree * gearbox)
                    pos_val_disp = 0 if abs(pos_val_deg) < 1e-6 else round(pos_val_deg, 2)
                    if not window_closed:
                        window[f'S{i}_actual_pos'].update(str(pos_val_disp))
                        update_setpoint_highlight(window, i, pos_val_deg)
                    window._last_valid_pos[i-1] = str(pos_val_disp)
                    window._invalid_resp_counters[i-1] = 0
                    valid = True
                except Exception:
                    pass
            # Actual position in pulses display
            if pos_resp is not None and str(pos_resp).strip() not in (':', ''):
                try:
                    pos_pulses_disp = str(pos_resp).strip()
                    if not window_closed:
                        window[f'S{i}_actual_pos_pulses'].update(pos_pulses_disp)
                except Exception:
                    if not window_closed:
                        window[f'S{i}_actual_pos_pulses'].update('N/A')
            # Stop motion if position exceeds soft limits (safety net for external motion sources)
            if pos_val_deg is not None:
                axis_units = AXIS_UNITS[axis_letter]
                min_val = axis_units['min']
                max_val = axis_units['max']
                if (pos_val_deg < min_val or pos_val_deg > max_val) and not window._limit_tripped[i-1]:
                    stop_key = f'S{i}_stop'
                    stop_cmd = COMMAND_MAP.get(stop_key)
                    if stop_cmd and comm:
                        try:
                            stop_cmd_val = stop_cmd if not callable(stop_cmd) else stop_cmd()
                            comm.send_command(stop_cmd_val)
                            if not window_closed:
                                window['DEBUG_LOG'].print(f'[WARN] Axis {axis_letter} exceeded limits ({min_val},{max_val}); sent stop command: {stop_cmd_val}')
                                # Visual + popup notification on first limit trip
                                window[f'S{i}_status_light'].update('●', text_color='#FF4500')  # Orange-red
                                window[f'S{i}_status_text'].update('Stopped (limit)', text_color='#FF4500')
                                sg.popup_ok(f'Axis {axis_letter} exceeded limits ({min_val} to {max_val}). Motion stopped.', keep_on_top=True, title='')
                        except Exception:
                            if not window_closed:
                                window['DEBUG_LOG'].print(f'[ERROR] Failed to send stop for axis {axis_letter}')
                    elif not comm and not window_closed:
                        window['DEBUG_LOG'].print(f'[WARN] Axis {axis_letter} exceeded limits but comm not initialized; no stop sent')
                        sg.popup_ok(f'Axis {axis_letter} exceeded limits ({min_val} to {max_val}) but comm not initialized; stop not sent.', keep_on_top=True, title='')
                    window._limit_tripped[i-1] = True
                elif window._limit_tripped[i-1] and min_val <= pos_val_deg <= max_val:
                    # Clear limit indicator when back inside bounds
                    window._limit_tripped[i-1] = False
                    if not window_closed:
                        window[f'S{i}_status_light'].update('●', text_color='#00FF00')
                        window[f'S{i}_status_text'].update('Enabled', text_color='#00FF00')
            if not valid:
                window._invalid_resp_counters[i-1] += 1
                if window._invalid_resp_counters[i-1] >= 5:
                    if not window_closed:
                        window[f'S{i}_actual_pos'].update('N/A')
                    log_val = 'N/A'
                else:
                    last_val = window._last_valid_pos[i-1] if window._last_valid_pos[i-1] else ''
                    if not window_closed:
                        window[f'S{i}_actual_pos'].update(last_val)
                    log_val = last_val if last_val else 'N/A'
            else:
                log_val = window._last_valid_pos[i-1]
            if not window_closed and LOG_POSITION_POLLS:
                window['DEBUG_LOG'].print(f'Axis {axis_letter}: MG _RP{axis_letter} -> {log_val}')
        continue
    # Zero Position button (handle early so it isn't swallowed by generic S*_action logic)
    if isinstance(event, str) and event.endswith('_zero_pos'):
        try:
            servo_num = int(event[1:event.index('_')])
            dp_args = [','] * 8
            dp_args[servo_num - 1] = '0'
            dp_cmd = f"DP {''.join(dp_args)}"
            print(f'[DEBUG] Sending zero position command: {dp_cmd}')
            if comm:
                response = comm.send_command(dp_cmd)
                print(f'[DEBUG] Response: {response}')
        except Exception as e:
            sg.popup_error(f'Error parsing servo number: {e}', keep_on_top=True)
        continue

    # Keypad button logic for numeric value entry
    if event in NUMERIC_KEYPAD_BUTTONS:
        parts = event.split('_')
        servo = parts[0]
        field = '_'.join(parts[1:-1])
        input_key = f'{servo}_{field}'
        current_val = values.get(input_key, '')
        try:
            current_val = round(float(current_val), 1)
        except (ValueError, TypeError):
            current_val = 0.0
        # Convert servo number to axis letter (1->A, 2->B, ...)
        axis_num = int(servo[1:]) if servo.startswith('S') else None
        axis_letter = chr(64 + axis_num) if axis_num and 1 <= axis_num <= 8 else None
        # For all numeric fields, use AXIS_UNITS min/max for the axis if available
        if axis_letter and axis_letter in AXIS_UNITS and field in ['abs_pos', 'rel_pos']:
            min_val = AXIS_UNITS[axis_letter]['min']
            max_val = AXIS_UNITS[axis_letter]['max']
            unit_label = 'Deg'
        else:
            min_val, max_val = NUMERIC_LIMITS.get(field, (0, 54000))
            unit_label = 'DPS' if field == 'speed' else ('DPS^2' if field in ['accel', 'decel'] else '')
        # Make popup title more descriptive with setpoint type
        field_titles = {
            'speed': 'Speed',
            'accel': 'Acceleration',
            'decel': 'Deceleration',
            'abs_pos': 'Absolute Position',
            'rel_pos': 'Relative Position',
        }
        field_title = field_titles.get(field, field.capitalize())
        popup_title = f'Enter {field_title} for Servo {servo} ({unit_label})'
        keypad = NumericKeypad(
            title=popup_title,
            current_value=current_val,
            axis_letter=axis_letter,
            font=GLOBAL_FONT,
            unit_label=unit_label,
            min_val=min_val,
            max_val=max_val
        )
        result = keypad.show()
        if result is not None:
            # Enforce min/max for PC keyboard edits as well
            if result < min_val or result > max_val:
                sg.popup_error(f"Value for {field} must be between {min_val} and {max_val}", keep_on_top=True)
            else:
                window[input_key].update(format_display_value(result))
                # Mark pending (not confirmed) until OK is pressed
                try:
                    serv_num = int(servo[1:])
                    if field == 'abs_pos':
                        update_setpoint_highlight(window, serv_num)
                    else:
                        set_pending_highlight(window, serv_num, field)
                except Exception:
                    pass
        continue

    # Restrict keyboard entries for numeric fields to digits, leading '-', and a single decimal (one digit precision)
    if event in NUMERIC_INPUT_KEYS:
        val = values.get(event, '')
        import re
        # Keep only digits, '-', and '.'
        filtered = re.sub(r'[^0-9\-.]', '', val)
        # Normalize sign to leading position only
        sign = '-' if filtered.startswith('-') else ''
        filtered = filtered[1:] if filtered.startswith('-') else filtered
        filtered = filtered.replace('-', '')
        # Enforce a single decimal point and only one digit after it
        if '.' in filtered:
            whole, frac = filtered.split('.', 1)
            frac = frac[:1]
            filtered = f"{sign}{whole}.{frac}"
        else:
            filtered = sign + filtered
        # If the filtered value differs from the input, update the field
        if filtered != val:
            window[event].update(filtered)
        # Clamp to axis min/max for PC keyboard entry (same limits as keypad)
        if filtered not in ('', '-', '.', '-.'):
            try:
                numeric_val = float(filtered)
                parts = event.split('_', 1)
                servo_part = parts[0] if len(parts) > 0 else ''
                field_part = parts[1] if len(parts) > 1 else ''
                servo_num = int(servo_part[1:]) if servo_part.startswith('S') else None
                axis_letter = AXIS_LETTERS[servo_num - 1] if servo_num and 1 <= servo_num <= 8 else None
                if axis_letter and axis_letter in AXIS_UNITS and field_part in ['abs_pos', 'rel_pos']:
                    min_val = AXIS_UNITS[axis_letter]['min']
                    max_val = AXIS_UNITS[axis_letter]['max']
                else:
                    min_val, max_val = NUMERIC_LIMITS.get(field_part, (0, 54000))
                clamped = round(max(min_val, min(max_val, numeric_val)), 1)
                if clamped != numeric_val:
                    window[event].update(format_display_value(clamped))
                if servo_num and field_part:
                    if field_part == 'abs_pos':
                        update_setpoint_highlight(window, servo_num)
                    else:
                        set_pending_highlight(window, servo_num, field_part)
            except Exception:
                pass
    # Only call handle_servo_event for setpoint OK buttons
    if isinstance(event, str) and event.startswith('S') and '_' in event:
        if event.endswith('_ok'):
            print(f'[DEBUG] Main loop routing event to handle_servo_event: {event}')
            handle_servo_event(event, values)
            continue
        # Otherwise, handle direct motor control buttons (Enable, Disable, Start, Stop, Jog) by reusing handle_servo_event
        # to ensure a single code path with consistent scaling logic.
        parts = event.split('_')
        if len(parts) == 2:
            servo_num = parts[0][1:]
            action = parts[1]
            axis_letter = AXIS_LETTERS[int(servo_num)-1]
            prev_log = window['DEBUG_LOG'].get()
            if not prev_log.endswith('\r\n') and not prev_log.endswith('\n'):
                prev_log += '\r\n'
            window['DEBUG_LOG'].print(f'Button clicked: S{servo_num}_{action} (Axis {axis_letter})')
            # Reuse the unified handler (handles jog scaling to pulses)
            handle_servo_event(event, values)
        continue
# -----------------------------
# Main event loop (now at the very end)
# -----------------------------
if __name__ == "__main__":
    while True:
        event, values = window.read(timeout=100)
        # Ensure counters are initialized before use
        if not hasattr(window, '_invalid_resp_counters'):
            window._invalid_resp_counters = [0]*8
        if not hasattr(window, '_last_valid_pos'):
            window._last_valid_pos = ['']*8
        if event == sg.WIN_CLOSED:
            window_closed = True
            break
        if event == 'POSITION_POLL':
            # Handle position update from background thread
            data = values[event] if event in values else None
            if data:
                i = data['servo']
                axis_letter = data['axis_letter']
                pos_resp = data.get('pos_resp')
                raw_resp = data.get('raw_resp')
                pos_val = None
                valid = False
                # Log the raw response for debugging (optional)
                if not window_closed and LOG_POSITION_POLLS:
                    window['DEBUG_LOG'].print(f'Axis {axis_letter}: MG _RP{axis_letter} raw response: {raw_resp}')
                if pos_resp is not None and str(pos_resp).strip() != ':' and str(pos_resp).strip() != '':
                    try:
                        pos_val_pulses = float(pos_resp)
                        axis_units = AXIS_UNITS[axis_letter]
                        pulses_per_degree = axis_units.get('scaling') or (axis_units.get('pulses', 0) / max(axis_units.get('degrees', 1), 1e-9))
                        if pulses_per_degree <= 0:
                            pulses_per_degree = 1
                        gearbox = axis_units.get('gearbox', 1)
                        pos_val_deg = pos_val_pulses / (pulses_per_degree * gearbox)
                        pos_val_disp = 0 if abs(pos_val_deg) < 1e-6 else round(pos_val_deg, 2)
                        if not window_closed:
                            window[f'S{i}_actual_pos'].update(str(pos_val_disp))
                            update_setpoint_highlight(window, i, pos_val_deg)
                        window._last_valid_pos[i-1] = str(pos_val_disp)
                        window._invalid_resp_counters[i-1] = 0
                        valid = True
                    except Exception:
                        pass
                if not valid:
                    window._invalid_resp_counters[i-1] += 1
                    if window._invalid_resp_counters[i-1] >= 5:
                        if not window_closed:
                            window[f'S{i}_actual_pos'].update('N/A')
                            window[f'S{i}_actual_pos_pulses'].update('N/A')
                        log_val = 'N/A'
                    else:
                        last_val = window._last_valid_pos[i-1] if window._last_valid_pos[i-1] else ''
                        if not window_closed:
                            window[f'S{i}_actual_pos'].update(last_val)
                            window[f'S{i}_actual_pos_pulses'].update('')
                        log_val = last_val if last_val else 'N/A'
                else:
                    log_val = window._last_valid_pos[i-1]
                if not window_closed and LOG_POSITION_POLLS:
                    window['DEBUG_LOG'].print(f'Axis {axis_letter}: MG _RP{axis_letter} -> {log_val}')
            continue
        # Motor control logic for servo buttons and OK buttons
        if isinstance(event, str) and event.startswith('S') and '_' in event:
            # If this is an OK button for any setpoint, delegate to handle_servo_event (logging is handled after command is sent)
            if event.endswith('_ok'):
                handle_servo_event(event, values)
                continue
            # Otherwise, handle direct motor control buttons (Enable, Disable, Start, Stop, Jog)
            parts = event.split('_')
            if len(parts) == 2:
                servo_num = parts[0][1:]
                action = parts[1]
                axis_letter = AXIS_LETTERS[int(servo_num)-1]
                prev_log = window['DEBUG_LOG'].get()
                if not prev_log.endswith('\r\n') and not prev_log.endswith('\n'):
                    prev_log += '\r\n'
                window['DEBUG_LOG'].print(f'Button clicked: S{servo_num}_{action} (Axis {axis_letter})')
                map_key = f'S{servo_num}_{action}'
                if map_key in COMMAND_MAP:
                    cmd_func = COMMAND_MAP[map_key]
                    if action == 'jog':
                        # Legacy jog button removed; ignore
                        break
                    else:
                        cmd = cmd_func if not callable(cmd_func) else None
                    print(f'[DEBUG] Sending command: {cmd}')
                    if comm and cmd:
                        response = comm.send_command(cmd)
                        print(f'[DEBUG] Response: {response}')
                        window['DEBUG_LOG'].print(f'[INFO] Sent {cmd} -> {response}')
        # Zero Position button
        if isinstance(event, str) and event.endswith('_zero_pos'):
            try:
                servo_num = int(event[1:event.index('_')])
                dp_args = [','] * 8
                dp_args[servo_num - 1] = '0'
                dp_cmd = f"DP {''.join(dp_args)}"
                print(f'[DEBUG] Sending zero position command: {dp_cmd}')
                if comm:
                    response = comm.send_command(dp_cmd)
                    print(f'[DEBUG] Response: {response}')
            except Exception as e:
                sg.popup_error(f'Error parsing servo number: {e}', keep_on_top=True)
            continue
