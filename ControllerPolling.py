"""
ControllerPolling.py

Background polling thread for servo position, torque, and enable/disable status.
Intended for use with ControllerGUI.py.

Exports:
    start_polling_thread(window, comm, comm_e=None, comm_h=None)
        - Starts the polling thread and returns the thread object.
    start_comm_health_thread(window, comm, comm_e=None, comm_h=None, interval=5.0)
        - Starts comm-link health polling and returns (thread, stop_event).
"""
import threading
import time
import re
import queue
import subprocess
import os


def _extract_numeric_response(resp_str):
    if not isinstance(resp_str, str):
        return None
    for line in resp_str.splitlines():
        value = line.strip()
        if re.fullmatch(r'-?\d+(?:\.\d+)?', value):
            return value
    return None


def _extract_clearcore_position(resp_str):
    """Best-effort extract of Axis E position from ClearCore payload variants."""
    if not isinstance(resp_str, str):
        return None
    payload = resp_str.strip()
    if not payload:
        return None
    # Canonical VALUES:<...> format
    if 'VALUES:' in payload:
        try:
            values = payload.split('VALUES:', 1)[1].split(',')
            if len(values) >= 3:
                return str(float(values[2].strip()))
        except Exception:
            pass
    # Key/value telemetry variants seen in field logs
    patterns = [
        r'S5P\s*=\s*([-+]?\d+(?:\.\d+)?)',
        r'S5P_ACT\s*=\s*([-+]?\d+(?:\.\d+)?)',
        r'S5P_SPT\s*=\s*([-+]?\d+(?:\.\d+)?)',
        r'POS(?:ITION)?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)',
    ]
    for pattern in patterns:
        m = re.search(pattern, payload, re.IGNORECASE)
        if m:
            return m.group(1)
    return None

def polling_thread_func(window, comm, comm_e, comm_h, stop_event):
    """
    Polls servo position, torque, and enable/disable status in the background.
    Sends updates to the GUI using window.write_event_value.
    
    Args:
        window: PySimpleGUI window object
        comm: Primary TCP controller comm object (TIM/RSI path for A-D)
        comm_e: ClearCore comm object (axis E)
        comm_h: MyActuator comm object (axis H)
        stop_event: Threading event to stop the polling loop
    """
    while not stop_event.is_set():
        # 2. Get active servo and axis
        active_tab = window['TABGROUP'].get() if 'TABGROUP' in window.AllKeysDict else 'TAB1'
        try:
            active_servo = int(str(active_tab).replace('TAB', ''))
        except Exception:
            active_servo = 1
        axis_letter = chr(64 + active_servo)
        is_clearcore_axis = axis_letter == 'E'
        
        # Route to correct comm object based on axis
        # [CHANGE 2026-03-24 14:54:00 -04:00] Route Axis E polling to ClearCore comm object.
        if axis_letter == 'H' and comm_h is not None:
            active_comm = comm_h
        elif axis_letter == 'E' and comm_e is not None:
            active_comm = comm_e
        else:
            active_comm = comm
        
        # 1. Flush the buffer before sending the position command
        if active_comm and hasattr(active_comm, 'message_queue'):
            try:
                while True:
                    active_comm.message_queue.get_nowait()
            except queue.Empty:
                pass
        
        # --- Commands and response variables for this poll cycle ---
        pos_cmd    = f'MG _RP{axis_letter}'
        torque_cmd = f'MG _TC{axis_letter}'
        status_cmd = f'MG _MO{axis_letter}'
        speed_cmd  = f'MG _SP{axis_letter}'
        pos_resp    = None
        torque_resp = None
        status_resp = None
        speed_resp  = None
        raw_resp_str = None
        if active_comm:
            try:
                # Check if this is MyActuator (CommMode5) - it returns responses directly, no retries needed
                is_myactuator = (active_comm.mode == 'CommMode5') if hasattr(active_comm, 'mode') else False

                # Position
                resp_direct = active_comm.send_command(pos_cmd)
                if isinstance(resp_direct, str):
                    resp_str = resp_direct.strip()

                    raw_resp_str = resp_str
                    pos_resp = _extract_numeric_response(resp_str)
                    if pos_resp is None and axis_letter == 'E':
                        pos_resp = _extract_clearcore_position(resp_str)
                # Only retry for non-MyActuator controllers (Galil serial, etc.)
                if pos_resp is None and not is_myactuator:
                    time.sleep(0.05)  # Reduced from 0.2s
                    for _ in range(3):  # Reduced from 5 retries
                        if stop_event.is_set():
                            break
                        try:
                            resp = active_comm.receive_response(timeout=0.1)  # Reduced from 0.2s
                            resp_str = str(resp).strip() if resp is not None else ''
                            parsed = _extract_numeric_response(resp_str)
                            if parsed is None and axis_letter == 'E':
                                parsed = _extract_clearcore_position(resp_str)
                            if parsed is not None:
                                pos_resp = parsed
                                raw_resp_str = resp_str
                            if pos_resp is not None:
                                break
                        except Exception:
                            pass
                # [CHANGE 2026-03-24 10:55:00 -04:00] Axis E fallback: prefer commanded target, then tracked position cache.
                if pos_resp is None and axis_letter == 'E':
                    try:
                        cached_pos = getattr(active_comm, 'clearcore_commanded_position', None)
                        if cached_pos is None:
                            cached_pos = getattr(active_comm, 'clearcore_last_position', None)
                        if cached_pos is not None:
                            pos_resp = str(cached_pos)
                            if not raw_resp_str:
                                raw_resp_str = f'CACHE:{cached_pos}'
                    except Exception:
                        pass
                if not is_clearcore_axis:
                    # Torque
                    resp_direct = active_comm.send_command(torque_cmd)
                    if isinstance(resp_direct, str):
                        resp_str = resp_direct.strip()
                        torque_resp = _extract_numeric_response(resp_str)
                    if torque_resp is None and not is_myactuator:
                        time.sleep(0.05)
                        for _ in range(2):  # Reduced from 3
                            if stop_event.is_set():
                                break
                            try:
                                resp = active_comm.receive_response(timeout=0.1)
                                resp_str = str(resp).strip() if resp is not None else ''
                                torque_resp = _extract_numeric_response(resp_str)
                                if torque_resp is not None:
                                    break
                            except Exception:
                                pass
                    # Status
                    resp_direct = active_comm.send_command(status_cmd)
                    if isinstance(resp_direct, str):
                        resp_str = resp_direct.strip()
                        status_resp = _extract_numeric_response(resp_str)
                    if status_resp is None and not is_myactuator:
                        time.sleep(0.05)
                        for _ in range(2):  # Reduced from 3
                            if stop_event.is_set():
                                break
                            try:
                                resp = active_comm.receive_response(timeout=0.1)
                                resp_str = str(resp).strip() if resp is not None else ''
                                status_resp = _extract_numeric_response(resp_str)
                                if status_resp is not None:
                                    break
                            except Exception:
                                pass
                    # Speed (Galil only; CommMode1)
                    resp_direct = active_comm.send_command(speed_cmd)
                    if isinstance(resp_direct, str):
                        resp_str = resp_direct.strip()
                        speed_resp = _extract_numeric_response(resp_str)
                    if speed_resp is None and not is_myactuator:
                        time.sleep(0.05)
                        for _ in range(2):  # Reduced from 3
                            if stop_event.is_set():
                                break
                            try:
                                resp = active_comm.receive_response(timeout=0.1)
                                resp_str = str(resp).strip() if resp is not None else ''
                                speed_resp = _extract_numeric_response(resp_str)
                                if speed_resp is not None:
                                    break
                            except Exception:
                                pass
            except Exception:
                pass
        # 4. Send result to GUI
        if pos_resp is not None or torque_resp is not None or status_resp is not None or speed_resp is not None:

            window.write_event_value(
                'POSITION_POLL',
                {
                    'servo': active_servo,
                    'axis_letter': axis_letter,
                    'pos_resp': pos_resp,
                    'raw_resp': raw_resp_str,
                    'torque_resp': torque_resp,
                    'status_resp': status_resp,
                    'speed_resp': speed_resp
                }
            )
        # 5. Flush the buffer after processing
        if active_comm and hasattr(active_comm, 'message_queue'):
            try:
                while True:
                    active_comm.message_queue.get_nowait()
            except queue.Empty:
                pass
        # 6. Wait before next cycle
        time.sleep(0.5)  # 500ms = 2 polls per second

def start_polling_thread(window, comm, comm_e=None, comm_h=None):
    """
    Starts the polling thread. Returns (thread, stop_event).
    
    Args:
        window: PySimpleGUI window object
        comm: Primary TCP controller comm object (TIM/RSI path for A-D)
        comm_e: ClearCore comm object (axis E), optional
        comm_h: MyActuator comm object (axis H), optional
    """
    stop_event = threading.Event()
    thread = threading.Thread(target=polling_thread_func, args=(window, comm, comm_e, comm_h, stop_event), daemon=True)
    thread.start()
    return thread, stop_event


# [CHANGE 2026-04-17 00:00:00 -04:00] Comm health polling thread: periodically pings each controller and reports link status.

# Which servo numbers belong to each controller group:
#   Primary TCP service (comm): S1-S4 (axes A-D)
#   ClearCore (comm_e): S5 (axis E)
#   MyActuator (comm_h): S8 (axis H)
#   Servos 6, 7: no comm object assigned → always 'unconfigured'
_RSI_SERVOS       = [1, 2, 3, 4]
_CLEARCORE_SERVOS = [5]
_MYACTUATOR_SERVOS = [8]
_UNCONFIGURED_SERVOS = [6, 7]


def _ping_rsi(comm):
    """Send a lightweight Galil query and return True if a valid reply arrives."""
    try:
        resp = comm.send_command('MG _GN')
        # A numeric string or any non-False/non-None reply counts as alive.
        return resp is not False and resp is not None
    except Exception:
        return False


def _ping_host(ip_address, timeout_seconds=0.8):
    """Return True when the controller host is reachable at the network layer."""
    if not ip_address:
        return False
    try:
        timeout_ms = max(1, int(timeout_seconds * 1000))
        if os.name == 'nt':
            cmd = ['ping', '-n', '1', '-w', str(timeout_ms), str(ip_address)]
        else:
            timeout_s = max(1, int(round(timeout_seconds)))
            cmd = ['ping', '-c', '1', '-W', str(timeout_s), str(ip_address)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=max(2.0, timeout_seconds + 1.0))
        return result.returncode == 0
    except Exception:
        return False


def _ping_clearcore(comm_e):
    """Ping ClearCore and require either a real controller reply or network reachability."""
    try:
        # [CHANGE 2026-04-17 00:00:00 -04:00] A UDP send alone cannot detect unplugged cable.
        # Prefer an actual controller reply; if the device is quiet, fall back to OS-level ping.
        resp = comm_e.send_command('REQUEST_BUTTON_STATES')
        resp_text = '' if resp is None else str(resp).strip()
        if resp not in (False, None) and resp_text not in ('', '0'):
            return True
    except Exception:
        pass

    return _ping_host(getattr(comm_e, 'clearcore_ip', None), timeout_seconds=0.8)


def _ping_myactuator(comm_h):
    """Ping MyActuator without invoking incomplete command paths that spam the terminal."""
    try:
        if not hasattr(comm_h, '_myact_send_command'):
            return False
        resp = comm_h.send_command('MG _RPA')
        return resp is not False and resp is not None
    except Exception:
        return False


def comm_health_thread_func(window, comm, comm_e, comm_h, stop_event, interval=5.0):
    """
    Periodically pings each controller and posts a COMM_HEALTH event to the GUI.
    Payload: dict mapping servo_num -> {'ok': bool, 'label': str}
    """
    while not stop_event.is_set():
        health = {}

        # RSI (axes 1-4)
        if comm is not None:
            ok = _ping_rsi(comm)
            label = 'Comms OK' if ok else 'No Link'
            for s in _RSI_SERVOS:
                health[s] = {'ok': ok, 'label': label}
        else:
            for s in _RSI_SERVOS:
                health[s] = {'ok': None, 'label': 'No Link'}

        # ClearCore (axis 5)
        if comm_e is not None:
            ok = _ping_clearcore(comm_e)
            label = 'Comms OK' if ok else 'No Link'
            for s in _CLEARCORE_SERVOS:
                health[s] = {'ok': ok, 'label': label}
        else:
            for s in _CLEARCORE_SERVOS:
                health[s] = {'ok': None, 'label': 'No Link'}

        # MyActuator (axis 8)
        if comm_h is not None:
            ok = _ping_myactuator(comm_h)
            label = 'Comms OK' if ok else 'No Link'
            for s in _MYACTUATOR_SERVOS:
                health[s] = {'ok': ok, 'label': label}
        else:
            for s in _MYACTUATOR_SERVOS:
                health[s] = {'ok': None, 'label': 'No Link'}

        # Unconfigured servos
        for s in _UNCONFIGURED_SERVOS:
            health[s] = {'ok': None, 'label': 'No Link'}

        try:
            window.write_event_value('COMM_HEALTH', health)
        except Exception:
            pass

        # Sleep in short increments so stop_event is respected promptly
        elapsed = 0.0
        while elapsed < interval and not stop_event.is_set():
            time.sleep(0.25)
            elapsed += 0.25


def start_comm_health_thread(window, comm, comm_e=None, comm_h=None, interval=5.0):
    """
    Starts the comm health polling thread. Returns (thread, stop_event).
    interval: seconds between pings (default 5).
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=comm_health_thread_func,
        args=(window, comm, comm_e, comm_h, stop_event),
        kwargs={'interval': interval},
        daemon=True
    )
    thread.start()
    return thread, stop_event
