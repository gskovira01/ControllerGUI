"""
ControllerPolling.py

Background polling thread for servo position, torque, and enable/disable status.
Intended for use with ControllerGUI.py.

Exports:
    start_polling_thread(window, comm)
        - Starts the polling thread and returns the thread object.
"""
import threading
import time
import re
import queue


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
        comm: Galil controller comm object (axes A-G)
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
        
        # --- Position ---
        pos_cmd = f'MG _RP{axis_letter}'
        pos_resp = None
        raw_resp_str = None
        # --- Torque (example: MG _TC{axis_letter}) ---
        torque_cmd = f'MG _TC{axis_letter}' if not is_clearcore_axis else None
        torque_resp = None
        # --- Enable/Disable Status (example: MG _MO{axis_letter}) ---
        status_cmd = f'MG _MO{axis_letter}' if not is_clearcore_axis else None
        status_resp = None
        # --- Actual speed (example: MG _SPE{axis_letter}) ---
        speed_cmd = f'MG _SPE{axis_letter}' if not is_clearcore_axis else None
        speed_resp = None
        # 3. Issue the requests
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
        comm: Galil controller comm object (axes A-G)
        comm_e: ClearCore comm object (axis E), optional
        comm_h: MyActuator comm object (axis H), optional
    """
    stop_event = threading.Event()
    thread = threading.Thread(target=polling_thread_func, args=(window, comm, comm_e, comm_h, stop_event), daemon=True)
    thread.start()
    return thread, stop_event
