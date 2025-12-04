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
# Dictionary mapping each field to its min and max values (same for all servos)
NUMERIC_LIMITS = {
    'speed': (0, 54000),
    'accel': (0, 54000),
    'decel': (0, 54000),
    'abs_pos': (0, 54000),
    'rel_pos': (-150000, 150000)
}
# Automatically generate command mappings for all 8 servos

# -----------------------------
# Command Mapping Dictionaries
# -----------------------------
# GALIL_COMMAND_MAP: Maps GUI actions to Galil controller commands (A-H axes)
# CLEARCORE_COMMAND_MAP: Maps GUI actions to ClearCore controller commands (1-8 axes)
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

CLEARCORE_COMMAND_MAP = {}
for i in range(1, 9):
    CLEARCORE_COMMAND_MAP[f'S{i}_enable'] = f'ENABLE_SERVO_{i}'
    CLEARCORE_COMMAND_MAP[f'S{i}_disable'] = f'DISABLE_SERVO_{i}'
    CLEARCORE_COMMAND_MAP[f'S{i}_start'] = f'START_MOTION_{i}'
    CLEARCORE_COMMAND_MAP[f'S{i}_stop'] = f'STOP_MOTION_{i}'
    CLEARCORE_COMMAND_MAP[f'S{i}_jog'] = (lambda speed, axis=i: f'JOG_SERVO_{axis}_{speed}')
    CLEARCORE_COMMAND_MAP[f'S{i}_speed'] = (lambda value, axis=i: f'SET_SPEED_{axis}_{value}')
    CLEARCORE_COMMAND_MAP[f'S{i}_accel'] = (lambda value, axis=i: f'SET_ACCEL_{axis}_{value}')
    CLEARCORE_COMMAND_MAP[f'S{i}_decel'] = (lambda value, axis=i: f'SET_DECEL_{axis}_{value}')
    CLEARCORE_COMMAND_MAP[f'S{i}_abs_pos'] = (lambda value, axis=i: f'SET_ABS_POS_{axis}_{value}')
    CLEARCORE_COMMAND_MAP[f'S{i}_rel_pos'] = (lambda value, axis=i: f'SET_REL_POS_{axis}_{value}')

# ===================== CONTROLLER TYPE SELECTION FROM INI =====================
###############################################################################
def get_controller_type_from_ini(ini_path='controller_config.ini'):
    """
    Reads the controller type from the INI file.
    Returns: 'CommMode1', 'CommMode2', 'CommMode3', or None
    """
    config = configparser.ConfigParser()
    if not os.path.exists(ini_path):
        return None
    config.read(ini_path)
    try:
        return config['Controller']['type'].strip()
    except Exception:
        return None

# Select command map based on ini file
# -----------------------------
# Select command map based on controller type from INI file
# -----------------------------
controller_type = get_controller_type_from_ini()
if controller_type in ('CommMode1', 'CommMode2'):
    COMMAND_MAP = GALIL_COMMAND_MAP
elif controller_type == 'CommMode3':
    COMMAND_MAP = CLEARCORE_COMMAND_MAP
else:
    COMMAND_MAP = GALIL_COMMAND_MAP  # Default fallback

# Parse INI and initialize ControllerComm with correct config
###############################################################################
# -----------------------------
# Initialize ControllerComm with correct config from INI file
# -----------------------------
comm = None
try:
    config = configparser.ConfigParser()
    config.read('controller_config.ini')
    try:
        if controller_type == 'CommMode1':
            galil_config = dict(config.items('CommMode1')) if config.has_section('CommMode1') else {}
            comm = ControllerComm(mode='CommMode1', galil_config=galil_config)
        elif controller_type == 'CommMode2':
            serial_config = dict(config.items('CommMode2')) if config.has_section('CommMode2') else {}
            # Convert numeric values
            if 'baudrate' in serial_config:
                serial_config['baudrate'] = int(serial_config['baudrate'])
            if 'timeout' in serial_config:
                serial_config['timeout'] = float(serial_config['timeout'])
            comm = ControllerComm(mode='CommMode2', serial_config=serial_config)
        elif controller_type == 'CommMode3':
            udp_config = dict(config.items('CommMode3')) if config.has_section('CommMode3') else {}
            if 'port1' in udp_config:
                udp_config['port1'] = int(udp_config['port1'])
            if 'local_port' in udp_config:
                udp_config['local_port'] = int(udp_config['local_port'])
            comm = ControllerComm(mode='CommMode3', udp_config=udp_config)
        else:
            comm = None
            sg.popup_error('Unknown controller type in INI file.', keep_on_top=True)
        print(f'[DEBUG] ControllerComm initialized: comm={comm}, mode={getattr(comm, "mode", None)}')
    except Exception as comm_error:
        comm = None
        import traceback
        error_details = f'{comm_error}\n' + traceback.format_exc()
        sg.popup_error(f'Failed to initialize controller communications:\n{comm_error}', keep_on_top=True)
        print(f'[ERROR] Failed to initialize controller communications: {error_details}')
except Exception as e:
    comm = None
    sg.popup_error(f'Failed to initialize controller communications: {e}', keep_on_top=True)

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
         sg.Button('⌨', key=f'S{servo_num}_speed_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_speed_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Acceleration:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_accel', size=(10,1), font=GLOBAL_FONT, enable_events=True),
         sg.Button('⌨', key=f'S{servo_num}_accel_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_accel_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Deceleration:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_decel', size=(10,1), font=GLOBAL_FONT, enable_events=True),
         sg.Button('⌨', key=f'S{servo_num}_decel_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_decel_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Absolute Position:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_abs_pos', size=(10,1), font=GLOBAL_FONT, enable_events=True),
         sg.Button('⌨', key=f'S{servo_num}_abs_pos_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_abs_pos_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Relative Position:', size=(18,1), font=GLOBAL_FONT),
         sg.Input(key=f'S{servo_num}_rel_pos', size=(10,1), font=GLOBAL_FONT, enable_events=True),
         sg.Button('⌨', key=f'S{servo_num}_rel_pos_keypad', size=(2,1), font=GLOBAL_FONT),
         sg.Button('OK', key=f'S{servo_num}_rel_pos_ok', size=(4,1), font=GLOBAL_FONT, button_color=('white', 'green'))],
        [sg.Text('Actual Position:', size=(18,1), font=GLOBAL_FONT), sg.Text('0', key=f'S{servo_num}_actual_pos', size=(10,1), font=GLOBAL_FONT)],
        [
            sg.Button('Servo Enable', key=f'S{servo_num}_enable', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Servo Disable', key=f'S{servo_num}_disable', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Zero Position', key=f'S{servo_num}_zero_pos', size=(12,2), font=GLOBAL_FONT)  # Default color (same as Jog)
        ],
        [
            sg.Button('Start Motion', key=f'S{servo_num}_start', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Stop Motion', key=f'S{servo_num}_stop', size=(12,2), font=GLOBAL_FONT),
            sg.Button('Jog', key=f'S{servo_num}_jog', size=(12,2), font=GLOBAL_FONT)
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
layout = [
    [
        sg.TabGroup([servo_tabs], key='TABGROUP', enable_events=True),
        sg.Push(),
        sg.Button('Shutdown', key='SHUTDOWN', size=(8,1), button_color=('white', 'red'), font=GLOBAL_FONT)
    ],
    [sg.Multiline('', key='DEBUG_LOG', size=(80, 8), font=('Courier New', 9), autoscroll=True, disabled=False, text_color='black', border_width=0)],
]
window = sg.Window("Controller GUI", layout, size=(700, 460), font=GLOBAL_FONT, finalize=True, return_keyboard_events=True)
###############################################################################
# Show popup if communications not initialized
###############################################################################
if comm is None:
    sg.popup_error('Controller communications not initialized. Check INI file and hardware connection.', keep_on_top=True)


# --- Define poll_and_update_indicator before it is called ---
def poll_and_update_indicator(axis_index):
###############################################################################
    axis_letter = AXIS_LETTERS[axis_index]
    status_cmd = f'MG _MO{axis_letter}'
    raw_resp = None
    if comm:
        try:
            # Clear out any old responses in the message queue before sending the status command
            if hasattr(comm, 'message_queue'):
                import queue
                try:
                    while True:
                        comm.message_queue.get_nowait()
                except queue.Empty:
                    pass
            comm.send_command(status_cmd)
            import re
            found_valid = False
            if hasattr(comm, 'mode') and comm.mode == 'CommMode2':
                for attempt in range(10):
                    resp = comm.receive_response(timeout=0.5)
                    if resp is None:
                        continue
                    resp = str(resp).strip()
                    if resp == ':' or not resp:
                        continue
                    # Look for a float (0.0 or 1.0) in the response
                    float_matches = re.findall(r'-?\d+\.\d+', resp)
                    if float_matches:
                        val = float(float_matches[0])
                        if abs(val) < 0.01 or abs(val - 1.0) < 0.01:
                            raw_resp = resp
                            found_valid = True
                            break
                if not found_valid:
                    raw_resp = None
            else:
                if hasattr(comm, 'message_queue'):
                    import queue
                    try:
                        for _ in range(10):
                            resp = str(comm.message_queue.get(timeout=0.5)).strip()
                            if resp == ':' or not resp:
                                continue
                            float_matches = re.findall(r'-?\d+\.\d+', resp)
                            if float_matches:
                                val = float(float_matches[0])
                                if abs(val) < 0.01 or abs(val - 1.0) < 0.01:
                                    raw_resp = resp
                                    found_valid = True
                                    break
                        if not found_valid:
                            raw_resp = None
                    except queue.Empty:
                        raw_resp = None
        except Exception:
            raw_resp = None
    indicator_text = '●'
    indicator_color = 'gray'
    status_text = 'Disabled'
    status_color = 'white'
    if raw_resp:
        import re
        float_matches = re.findall(r'-?\d+\.\d+', raw_resp)
        if float_matches:
            try:
                val = float(float_matches[0])
                if abs(val) < 0.01:
                    indicator_color = '#00FF00'  # Bright green for enabled
                    status_text = 'Enabled'
                    status_color = 'white'
                elif abs(val - 1.0) < 0.01:
                    indicator_color = '#FFFF00'  # Bright yellow for disabled
                    status_text = 'Disabled'
                    status_color = 'white'
                else:
                    indicator_color = 'gray'
                    status_text = 'Disabled'
                    status_color = 'white'
            except Exception:
                indicator_color = 'gray'
                status_text = 'Disabled'
                status_color = 'white'
    window[f'S{axis_index+1}_status_light'].update('●', text_color=indicator_color)
    window[f'S{axis_index+1}_status_text'].update(status_text, text_color=status_color)

def handle_servo_event(event, values):
    """
    Handles all servo-related button events (enable, disable, jog, set values).
    Args:
        event (str): Event key from PySimpleGUI
        values (dict): Current values from the GUI
    """
    for i in range(1, 9):
        prefix = f'S{i}_'
        # Handle OK buttons for each field
        for field in ['speed', 'accel', 'decel', 'abs_pos', 'rel_pos']:
            if event == f'S{i}_{field}_ok':
                map_key = f'S{i}_{field}'
                value = values.get(f'S{i}_{field}', None)
                if value is None or value == '':
                    sg.popup_error(f'Please enter a value for {field}', keep_on_top=True)
                    return
                try:
                    value = int(value)
                except ValueError:
                    sg.popup_error(f'Invalid value for {field}', keep_on_top=True)
                    return
                # Validate min/max for this field
                min_val, max_val = NUMERIC_LIMITS.get(field, (0, 54000))
                if not (min_val <= value <= max_val):
                    sg.popup_error(f'Value for {field} must be between {min_val} and {max_val}', keep_on_top=True)
                    return
                cmd_func = COMMAND_MAP[map_key]
                if callable(cmd_func):
                    cmd = cmd_func(value)
                else:
                    cmd = cmd_func
                # Send command to controller
                if comm:
                    try:
                        response = comm.send_command(cmd)
                        # Log request and reply in DEBUG_LOG
                        prev_log = window['DEBUG_LOG'].get()
                        new_log = f"Sent: {cmd}\nReply: {response}"
                        window['DEBUG_LOG'].update(prev_log + new_log + "\n")
                        sg.popup(f'Sent: {cmd}\nResponse: {response}', keep_on_top=True)
                    except Exception as e:
                        sg.popup_error(f'Error sending command: {e}', keep_on_top=True)
                else:
                    sg.popup_error('Controller communications not initialized.', keep_on_top=True)
                return
        # Handle other direct button events (Enable, Disable, Start, Stop, Jog)
        if event.startswith(prefix) and event[len(prefix):] in ['enable', 'disable', 'start', 'stop', 'jog']:
            action = event[len(prefix):]
            map_key = f'S{i}_{action}'
            if map_key in COMMAND_MAP:
                cmd = None
                if action == 'jog':
                    speed_val = values.get(f'S{i}_speed', None)
                    if speed_val is None or speed_val == '':
                        sg.popup_error('Please enter a speed value for Jog', keep_on_top=True)
                        return
                    try:
                        speed_val = int(speed_val)
                    except ValueError:
                        sg.popup_error('Invalid speed value for Jog', keep_on_top=True)
                        return
                    cmd_func = COMMAND_MAP[map_key]
                    if callable(cmd_func):
                        cmd = cmd_func(speed_val)
                    else:
                        cmd = cmd_func
                else:
                    cmd = COMMAND_MAP[map_key] if not callable(COMMAND_MAP[map_key]) else None
                if cmd:
                    # Send command to controller
                    if comm:
                        try:
                            response = comm.send_command(cmd)
                            # Log request and reply in DEBUG_LOG
                            prev_log = window['DEBUG_LOG'].get()
                            new_log = f"Sent: {cmd}\nReply: {response}"
                            window['DEBUG_LOG'].update(prev_log + new_log + "\n")
                            sg.popup(f'Sent: {cmd}\nResponse: {response}', keep_on_top=True)
                            # Immediately poll and update indicator for this servo if enable/disable
                            if action in ['enable', 'disable']:
                                poll_and_update_indicator(i-1)
                        except Exception as e:
                            sg.popup_error(f'Error sending command: {e}', keep_on_top=True)
                    else:
                        sg.popup_error('Controller communications not initialized.', keep_on_top=True)
            return

# Helper function to poll and update the currently active servo indicator
def poll_active_servo_indicator(window, comm, values=None):
    """
    Polls the currently active servo tab and updates its indicator.
    Args:
        window: The PySimpleGUI window object
        comm: The controller communication object
        values: The current values dict (optional, for tab selection)
    """
    active_tab = None
    if values and 'TABGROUP' in values:
        active_tab = values['TABGROUP']
    elif 'TABGROUP' in window.AllKeysDict:
        active_tab = window['TABGROUP'].get()
    active_servo = 1
    if active_tab:
        try:
            active_servo = int(active_tab.replace('TAB', ''))
        except Exception:
            active_servo = 1
    poll_and_update_indicator(active_servo - 1)


# --- Update status indicator for the active servo on startup ---
try:
    poll_active_servo_indicator(window, comm)
except Exception as e:
    window['DEBUG_LOG'].update(f'Error updating indicator on startup: {e}')


# --- Update status indicator for the active servo on startup ---
try:
    poll_active_servo_indicator(window, comm)
except Exception as e:
    window['DEBUG_LOG'].update(f'Error updating indicator on startup: {e}')


# -----------------------------
# Main event loop
# -----------------------------
while True:
    print('[DEBUG] Main event loop running')
    event, values = window.read(timeout=2000)
    poll_now = False
    if event is None or event == '__TIMEOUT__':
        poll_now = True
    elif event == 'TABGROUP':
        poll_now = True
    print(f'[DEBUG] event={event}, poll_now={poll_now}')
    if event == sg.WIN_CLOSED:
        break
    if poll_now:
        print('[POLL] Entered poll_now block')
        print('[POLL] Polling only the active servo for actual position...')
        # --- Add counters for consecutive invalid responses ---
        if not hasattr(window, '_invalid_resp_counters'):
            window._invalid_resp_counters = [0]*8  # One for each axis
        if not hasattr(window, '_last_valid_pos'):
            window._last_valid_pos = ['']*8
        try:
            try:
                poll_active_servo_indicator(window, comm, values)
            except Exception as e:
                print(f'[POLL] Exception in poll_active_servo_indicator: {e}')
            print('[POLL] After poll_active_servo_indicator, before MG _RPx for active tab')
            # Determine active tab/servo
            active_tab = None
            if values and 'TABGROUP' in values:
                active_tab = values['TABGROUP']
            elif 'TABGROUP' in window.AllKeysDict:
                active_tab = window['TABGROUP'].get()
            active_servo = 1
            if active_tab:
                try:
                    active_servo = int(str(active_tab).replace('TAB', ''))
                except Exception:
                    active_servo = 1
            i = active_servo
            axis_letter = chr(64 + i)
            try:
                pos_cmd = f'MG _RP{axis_letter}'
                print(f'[POLL] Sending: {pos_cmd}')
                send_result = comm.send_command(pos_cmd)
                print(f'[POLL] send_command result: {send_result}')
                pos_resp = None
                while True:
                    try:
                        resp = comm.receive_response(timeout=0.1)
                        if resp is not None:
                            pos_resp = resp
                        else:
                            break
                    except Exception as ex:
                        print(f'[POLL] Exception in receive_response: {ex}')
                        break
                print(f'[POLL] {pos_cmd} response: {pos_resp}')
                prev_log = window['DEBUG_LOG'].get()
                window['DEBUG_LOG'].update(prev_log + f'[POLL] Sent: {pos_cmd}\n[POLL] Response: {repr(pos_resp)}\n')
                # --- Only show 'N/A' after 5 consecutive invalid responses ---
                import re
                pos_val = None
                valid = False
                if pos_resp is not None and str(pos_resp).strip() != ':' and str(pos_resp).strip() != '':
                    match = re.search(r'(-?\d+\.\d+)', str(pos_resp))
                    if match:
                        pos_val = match.group(1)
                        try:
                            pos_val_num = int(float(pos_val))
                        except Exception:
                            pos_val_num = pos_val
                        window[f'S{i}_actual_pos'].update(str(pos_val_num))
                        window._last_valid_pos[i-1] = str(pos_val_num)
                        window._invalid_resp_counters[i-1] = 0
                        valid = True
                if not valid:
                    window._invalid_resp_counters[i-1] += 1
                    if window._invalid_resp_counters[i-1] >= 5:
                        window[f'S{i}_actual_pos'].update('N/A')
                        log_val = 'N/A'
                    else:
                        # Show last valid value, or blank if none
                        last_val = window._last_valid_pos[i-1] if window._last_valid_pos[i-1] else ''
                        window[f'S{i}_actual_pos'].update(last_val)
                        log_val = last_val if last_val else 'N/A'
                else:
                    log_val = window._last_valid_pos[i-1]
                prev_log = window['DEBUG_LOG'].get()
                window['DEBUG_LOG'].update(prev_log + f'Axis {axis_letter}: {pos_cmd} -> {log_val}\n')
            except Exception as e:
                print(f'[POLL] Exception in polling loop for axis {axis_letter}: {e}')
                window[f'S{i}_actual_pos'].update('N/A')
                prev_log = window['DEBUG_LOG'].get()
                window['DEBUG_LOG'].update(prev_log + f'Axis {axis_letter}: ERROR {e}\n')
        except Exception as e:
            print(f'[POLL] Exception in poll_now block: {e}')
            window['DEBUG_LOG'].update(f'Error polling indicator/position: {e}')
        continue
    # Show numeric keypad when keypad button is clicked
    if event in NUMERIC_KEYPAD_BUTTONS:
        # event is like 'S1_speed_keypad', extract field and servo
        parts = event.split('_')
        servo = parts[0]
        field = '_'.join(parts[1:-1])
        input_key = f'{servo}_{field}'
        current_val = values.get(input_key, '')
        try:
            current_val = int(current_val)
        except (ValueError, TypeError):
            current_val = 0
        # Lookup min and max for this field from NUMERIC_LIMITS
        min_val, max_val = NUMERIC_LIMITS.get(field, (0, 54000))
        keypad = NumericKeypad(
            title=f'Enter value for {input_key}',
            current_value=current_val,
            min_val=min_val,
            max_val=max_val,
            font=GLOBAL_FONT
        )
        result = keypad.show()
        if result is not None:
            window[input_key].update(str(result))
        continue
    # Handle Zero Position button
    if isinstance(event, str) and event.endswith('_zero_pos'):
        # event is like 'S1_zero_pos', extract servo number
        try:
            servo_num = int(event[1:event.index('_')])
            # DP command for single axis: DP n (n is the value for the axis, others omitted)
            # For axis A=1, DP 0,,,,,,,
            dp_args = [','] * 8
            dp_args[servo_num - 1] = '0'
            dp_cmd = f"DP {''.join(dp_args)}"
            if comm:
                try:
                    response = comm.send_command(dp_cmd)
                    prev_log = window['DEBUG_LOG'].get()
                    window['DEBUG_LOG'].update(prev_log + f'Sent: {dp_cmd}\nReply: {response}\n')
                    sg.popup(f'Sent: {dp_cmd}\nResponse: {response}', keep_on_top=True)
                except Exception as e:
                    sg.popup_error(f'Error sending DP command: {e}', keep_on_top=True)
            else:
                sg.popup_error('Controller communications not initialized.', keep_on_top=True)
        except Exception as e:
            sg.popup_error(f'Error parsing servo number: {e}', keep_on_top=True)
        continue
    # Handle all servo button events (but not input field changes)
    if isinstance(event, str) and event.startswith('S') and '_' in event and not event.endswith(tuple(['speed','accel','decel','abs_pos','rel_pos'])):
        handle_servo_event(event, values)
    # ...existing code for other events...
window.close()