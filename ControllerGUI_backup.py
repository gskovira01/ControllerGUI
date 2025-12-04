"""
================================================================================
                         CONTROLLER GUI SYSTEM (MINIMAL)
================================================================================

PURPOSE:
    Minimal GUI starter for controller interface, with main window and numeric keypad popup.
    Based on Servo_Control_8_Axis.py window and popup logic.

    Features:
    - Tabbed interface for 8 servos
    - Numeric keypad popup for value entry
    - Dynamic command mapping for Galil and ClearCore controllers
    - Periodic status polling and indicator lights for each servo
================================================================================
"""

# ============================================================================
# Imports and Configuration
# ============================================================================
import FreeSimpleGUI as sg
import threading  # For future use if needed
import platform                            # Cross-platform OS detection and adaptation
import configparser
import os
from communications import ControllerComm

# ============================================================================
# Constants and Global Variables
# ============================================================================
import FreeSimpleGUI as sg
import threading  # For future use if needed
import platform                            # Cross-platform OS detection and adaptation
import configparser
import os
from communications import ControllerComm


# ============================================================================
#                         PLATFORM DETECTION & CONFIGURATION
# ============================================================================

# Cross-platform compatibility flags
IS_WINDOWS = platform.system() == "Windows"      # Windows development environment
IS_RASPBERRY_PI = platform.system() == "Linux" and platform.machine().startswith('arm')  # Pi deployment


GLOBAL_FONT = ('Courier New', 10)
POSITION_LABEL_FONT = ('Courier New', 10, 'bold')
CLEAR_BUTTON_FONT = ('Courier New', 9)
POSITION_LIMITS = {1: (0, 180), 2: (0, 180), 3: (0, 180), 4: (0, 180), 5: (0, 180), 6: (0, 180), 7: (0, 180), 8: (0, 180)}


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
    return [
        [sg.Text(f'Servo {servo_num}', font=POSITION_LABEL_FONT),
         sg.Text('●', key=f'S{servo_num}_status_light', font=('Courier New', 16), text_color='gray')],
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
        [sg.Button('Servo Enable', key=f'S{servo_num}_enable', size=(14,2), font=GLOBAL_FONT),
         sg.Button('Servo Disable', key=f'S{servo_num}_disable', size=(14,2), font=GLOBAL_FONT)],
        [sg.Button('Start Motion', key=f'S{servo_num}_start', size=(14,2), font=GLOBAL_FONT),
         sg.Button('Stop Motion', key=f'S{servo_num}_stop', size=(14,2), font=GLOBAL_FONT),
         sg.Button('Jog', key=f'S{servo_num}_jog', size=(14,2), font=GLOBAL_FONT)]
    ]

def show_numeric_keypad(title, current_value, min_val=0, max_val=54000):
###############################################################################
    """
    Custom numeric keypad popup for touchscreen input.
    Args:
        title (str): Popup window title
        current_value (int): Initial value to display
        min_val (int): Minimum allowed value
        max_val (int): Maximum allowed value
    Returns:
        int or None: Entered value or None if cancelled
    """
    layout = [
        [sg.Text(title, font=GLOBAL_FONT)],
        [sg.Text('Current Value:', font=GLOBAL_FONT), 
         sg.InputText(str(current_value), key='display', size=(15, 1), font=GLOBAL_FONT, justification='center', readonly=False)],
        [sg.Button('7', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('8', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('9', size=(6, 2), font=GLOBAL_FONT)],
        [sg.Button('4', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('5', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('6', size=(6, 2), font=GLOBAL_FONT)],
        [sg.Button('1', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('2', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('3', size=(6, 2), font=GLOBAL_FONT)],
        [sg.Button('Clear', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('0', size=(6, 2), font=GLOBAL_FONT), 
         sg.Button('⌫', size=(6, 2), font=GLOBAL_FONT)],
        [sg.Button('Cancel', size=(8, 2), font=GLOBAL_FONT), 
         sg.Button('OK', size=(8, 2), font=GLOBAL_FONT)]
    ]
    # Upper right corner positioning for all platforms
    location = (50, 50)  # Upper left corner for all platforms
    popup_window = sg.Window(title, layout, modal=True, finalize=True, location=location, keep_on_top=True)
    while True:
        event, values = popup_window.read()
        if event in (sg.WIN_CLOSED, 'Cancel'):
            popup_window.close()
            return None
        elif event == 'OK':
            try:
                result = int(values['display'])
                if min_val <= result <= max_val:
                    popup_window.close()
                    return result
                else:
                    sg.popup_error(f'Value must be between {min_val} and {max_val}', keep_on_top=True, location=(50, 50), font=GLOBAL_FONT)
            except ValueError:
                sg.popup_error('Please enter a valid number', keep_on_top=True, location=(50, 50), font=GLOBAL_FONT)
        elif event == 'Clear':
            popup_window['display'].update('0')
        elif event == '⌫':  # Backspace
            current = values['display']
            popup_window['display'].update(current[:-1])
        elif event in '0123456789':
            current = values['display']
            popup_window['display'].update(current + event)


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
    [sg.TabGroup([servo_tabs], key='TABGROUP', enable_events=True)],
    [sg.Text(' ', size=(60, 1), font=GLOBAL_FONT),
     sg.Button('Test Status Poll', key='TEST_STATUS_POLL', size=(16,2), button_color=('white', 'blue'), font=GLOBAL_FONT),
     sg.Button('Shutdown', key='SHUTDOWN', size=(14,2), button_color=('white', 'red'), font=GLOBAL_FONT)],
    # Status/debug window always at the bottom
    [sg.Multiline('', key='DEBUG_LOG', size=(80, 8), font=('Courier New', 9), autoscroll=True, disabled=True)]
]
window = sg.Window("Controller GUI", layout, size=(700, 550), font=GLOBAL_FONT, finalize=True, return_keyboard_events=True)
###############################################################################


# Show popup if communications not initialized
###############################################################################
if comm is None:
    sg.popup_error('Controller communications not initialized. Check INI file and hardware connection.', keep_on_top=True)

# --- Update status indicator for the active servo on startup (after function is defined) ---
###############################################################################
try:
    # Default to first servo tab if none selected
    active_tab = window['TABGROUP'].get() if 'TABGROUP' in window.AllKeysDict else None
    active_servo = 1
    if active_tab:
        try:
            active_servo = int(active_tab.replace('TAB', ''))
        except Exception:
            active_servo = 1
    poll_and_update_indicator(active_servo - 1)
except Exception as e:
    window['DEBUG_LOG'].update(f'Error updating indicator on startup: {e}')


def poll_and_update_indicator(axis_index):
###############################################################################
    axis_letter = AXIS_LETTERS[axis_index]
    status_cmd = f'MG _MO{axis_letter}'
    raw_resp = None
    if comm:
        try:
            comm.send_command(status_cmd)
            if hasattr(comm, 'mode') and comm.mode == 'CommMode2':
                for attempt in range(5):
                    resp = comm.receive_response(timeout=0.5)
                    if resp is None:
                        continue
                    resp = str(resp).strip()
                    if resp == ':':
                        continue
                    raw_resp = resp
                    break
            else:
                if hasattr(comm, 'message_queue'):
                    import queue
                    try:
                        raw_resp = str(comm.message_queue.get(timeout=0.5)).strip()
                    except queue.Empty:
                        raw_resp = None
        except Exception:
            raw_resp = None
    indicator_text = '●'
    indicator_color = 'gray'
    if raw_resp:
        import re
        float_matches = re.findall(r'-?\d+\.\d+', raw_resp)
        if float_matches:
            try:
                val = float(float_matches[0])
                if abs(val) < 0.01:
                    indicator_color = '#00FF00'  # Bright green for enabled
                elif abs(val - 1.0) < 0.01:
                    indicator_color = '#FFFF00'  # Bright yellow for disabled
                else:
                    indicator_color = 'gray'
            except Exception:
                indicator_color = 'gray'
    window[f'S{axis_index+1}_status_light'].update('●', text_color=indicator_color)

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
                cmd_func = COMMAND_MAP[map_key]
                if callable(cmd_func):
                    cmd = cmd_func(value)
                else:
                    cmd = cmd_func
                # Send command to controller
                if comm:
                    try:
                        response = comm.send_command(cmd)
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
    # Poll every 5 seconds for status updates
    event, values = window.read(timeout=5000)
    if event == sg.WIN_CLOSED:
        break
    # Periodically query servo enable status every 2 seconds
    poll_now = False
    if event is None or event == 'TEST_STATUS_POLL':
        poll_now = True
    elif event == 'TABGROUP':
        poll_now = True
    if poll_now:
        try:
            poll_active_servo_indicator(window, comm, values)
        except Exception as e:
            window['DEBUG_LOG'].update(f'Error polling indicator: {e}')
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
        min_val, max_val = 0, 54000
        if 'abs_pos' in field or 'rel_pos' in field:
            min_val, max_val = 0, 180
        result = show_numeric_keypad(f'Enter value for {input_key}', current_val, min_val, max_val)
        if result is not None:
            window[input_key].update(str(result))
        continue
    # Handle all servo button events (but not input field changes)
    if isinstance(event, str) and event.startswith('S') and '_' in event and not event.endswith(tuple(['speed','accel','decel','abs_pos','rel_pos'])):
        handle_servo_event(event, values)
    # ...existing code for other events...
window.close()