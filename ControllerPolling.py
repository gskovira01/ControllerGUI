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

def polling_thread_func(window, comm, stop_event):
    """
    Polls servo position, torque, and enable/disable status in the background.
    Sends updates to the GUI using window.write_event_value.
    """
    while not stop_event.is_set():
        # 1. Flush the buffer before sending the position command
        if comm and hasattr(comm, 'message_queue'):
            try:
                while True:
                    comm.message_queue.get_nowait()
            except queue.Empty:
                pass
        # 2. Get active servo and axis
        active_tab = window['TABGROUP'].get() if 'TABGROUP' in window.AllKeysDict else 'TAB1'
        try:
            active_servo = int(str(active_tab).replace('TAB', ''))
        except Exception:
            active_servo = 1
        axis_letter = chr(64 + active_servo)
        # --- Position ---
        pos_cmd = f'MG _RP{axis_letter}'
        pos_resp = None
        raw_resp_str = None
        # --- Torque (example: MG _TC{axis_letter}) ---
        torque_cmd = f'MG _TC{axis_letter}'
        torque_resp = None
        # --- Enable/Disable Status (example: MG _MO{axis_letter}) ---
        status_cmd = f'MG _MO{axis_letter}'
        status_resp = None
        # --- Actual speed (example: MG _SPE{axis_letter}) ---
        speed_cmd = f'MG _SPE{axis_letter}'
        speed_resp = None
        # 3. Issue the requests
        if comm:
            try:
                # Position
                resp_direct = comm.send_command(pos_cmd)
                if isinstance(resp_direct, str):
                    resp_str = resp_direct.strip()
                    raw_resp_str = resp_str
                    for line in resp_str.splitlines():
                        line = line.strip()
                        if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                            pos_resp = line
                            break
                if pos_resp is None:
                    time.sleep(0.2)
                    for _ in range(5):
                        if stop_event.is_set():
                            break
                        try:
                            resp = comm.receive_response(timeout=0.2)
                            resp_str = str(resp).strip() if resp is not None else ''
                            for line in resp_str.splitlines():
                                line = line.strip()
                                if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                                    pos_resp = line
                                    raw_resp_str = line
                                    break
                            if pos_resp is not None:
                                break
                        except Exception:
                            pass
                # Torque
                resp_direct = comm.send_command(torque_cmd)
                if isinstance(resp_direct, str):
                    resp_str = resp_direct.strip()
                    for line in resp_str.splitlines():
                        line = line.strip()
                        if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                            torque_resp = line
                            break
                if torque_resp is None:
                    time.sleep(0.1)
                    for _ in range(3):
                        if stop_event.is_set():
                            break
                        try:
                            resp = comm.receive_response(timeout=0.2)
                            resp_str = str(resp).strip() if resp is not None else ''
                            for line in resp_str.splitlines():
                                line = line.strip()
                                if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                                    torque_resp = line
                                    break
                            if torque_resp is not None:
                                break
                        except Exception:
                            pass
                # Status
                resp_direct = comm.send_command(status_cmd)
                if isinstance(resp_direct, str):
                    resp_str = resp_direct.strip()
                    for line in resp_str.splitlines():
                        line = line.strip()
                        if re.fullmatch(r'-?\d+\.\d+', line):
                            status_resp = line
                            break
                if status_resp is None:
                    time.sleep(0.1)
                    for _ in range(3):
                        if stop_event.is_set():
                            break
                        try:
                            resp = comm.receive_response(timeout=0.2)
                            resp_str = str(resp).strip() if resp is not None else ''
                            for line in resp_str.splitlines():
                                line = line.strip()
                                if re.fullmatch(r'-?\d+\.\d+', line):
                                    status_resp = line
                                    break
                            if status_resp is not None:
                                break
                        except Exception:
                            pass
                # Speed (Galil only; CommMode1)
                resp_direct = comm.send_command(speed_cmd)
                if isinstance(resp_direct, str):
                    resp_str = resp_direct.strip()
                    for line in resp_str.splitlines():
                        line = line.strip()
                        if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                            speed_resp = line
                            break
                if speed_resp is None:
                    time.sleep(0.1)
                    for _ in range(3):
                        if stop_event.is_set():
                            break
                        try:
                            resp = comm.receive_response(timeout=0.2)
                            resp_str = str(resp).strip() if resp is not None else ''
                            for line in resp_str.splitlines():
                                line = line.strip()
                                if re.fullmatch(r'-?\d{1,7}\.\d+$', line):
                                    speed_resp = line
                                    break
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
        if comm and hasattr(comm, 'message_queue'):
            try:
                while True:
                    comm.message_queue.get_nowait()
            except queue.Empty:
                pass
        # 6. Wait before next cycle
        time.sleep(0.2)

def start_polling_thread(window, comm):
    """
    Starts the polling thread. Returns (thread, stop_event).
    """
    stop_event = threading.Event()
    thread = threading.Thread(target=polling_thread_func, args=(window, comm, stop_event), daemon=True)
    thread.start()
    return thread, stop_event
