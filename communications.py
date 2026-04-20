import logging
import socket
import queue
import threading
import time

logging.basicConfig(filename='controller_comm.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')

"""
================================================================================
CONTROLLER COMMUNICATIONS MODULE - REVISION 1.4
Unified Interface for RSI, ClearCore, MyActuator (Configurable Modes)
================================================================================

PURPOSE:
Provides a modular, unified interface for sending and receiving commands to industrial servo controllers:
- CommMode1: RSI Software via TCP for Axes A-D (Servos 1-4)
- CommMode6: ClearCore Board 1 via UDP for Axis E (Servo 5)
- CommMode5: MyActuator via Waveshare CAN-to-ETH TCP for Axis H

MODES:
- mode='CommMode1': RSI Software TCP (Axes A-D)
- mode='CommMode6': ClearCore Board 1 UDP (Axis E)
- mode='CommMode5': MyActuator CAN-to-ETH TCP (Axis H)

REVISION HISTORY
================================================================================

Rev 1.4.0 - March 22, 2026 - Add RSI Software support for Axes A-D
    - Replaced Galil gclib support with RSI TCP socket communication
    - RSI Software controls Servos 1-4 (Axes A-D) on dedicated PC400 Windows 11 PC
    - IP: 192.168.1.100:503 (TCP)
    - ASCII command protocol with \r\n terminators
    - Integration with ClearCore Board 1 (Axis E) architecture

Rev 1.3.0 - March 22, 2026 - Add ClearCore Board 1 support
    - Added CommMode6 for ClearCore controlling Axis E (Servo 5)
    - Command translation from Galil-style to ClearCore protocol
    
================================================================================
"""

logging.info('ControllerComm module loaded. Logging initialized.')

class ControllerComm:
    def __init__(self, mode='CommMode1', udp_config=None, serial_config=None, galil_config=None, 
                 rmp_config=None, myactuator_config=None, clearcore_config=None, rsi_config=None):
        """
        Initialize the ControllerComm class for various communication modes.
        Args:
            mode (str): 'CommMode1' for RSI Software, 'CommMode5' for MyActuator,
                       'CommMode6' for ClearCore Board 1 (Axis E)
            rsi_config (dict): RSI configuration (ip_address, port) - CommMode1
            clearcore_config (dict): ClearCore Board 1 configuration (ip_address, port) - CommMode6
            myactuator_config (dict): MyActuator configuration (ip, port, motor_id) - CommMode5
        """
        self.mode = mode if mode in ['CommMode1', 'CommMode5', 'CommMode6'] else 'CommMode1'
        self.rsi_config = rsi_config or {}
        self.clearcore_config = clearcore_config or {}
        self.myactuator_config = myactuator_config or {}
        self.message_queue = queue.Queue()
        self._lock = threading.Lock()
        
        if self.mode == 'CommMode1':
            self._init_rsi()
        elif self.mode == 'CommMode6':
            self._init_clearcore()
        elif self.mode == 'CommMode5':
            self._init_myactuator()

    # [CHANGE 2026-03-22] NEW METHOD: Initialize RSI Software TCP connection
    def _init_rsi(self):
        """
        Initialize CommMode1 TCP connection used for A-D command/telemetry path.
        Endpoint is driven by [CommMode1] values from controller_config.ini.
        Protocol: TCP with ASCII command set.
        """
        ip = self.rsi_config.get('ip_address', '192.168.1.100')
        port = int(self.rsi_config.get('port', 503))

        try:
            self.rsi_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rsi_sock.settimeout(2.0)
            self.rsi_sock.connect((ip, port))
            logging.info(f"RSI Software connected: {ip}:{port}")
        except Exception as e:
            msg = f"[ERROR] Communications Error (RSI): {e}"
            print(msg)
            logging.error(msg)
            self.rsi_sock = None

    def _reconnect_rsi(self):
        """Drop the broken socket and attempt one reconnect. Returns True on success."""
        try:
            if self.rsi_sock is not None:
                try:
                    self.rsi_sock.close()
                except Exception:
                    pass
                self.rsi_sock = None
            self._init_rsi()
            return self.rsi_sock is not None
        except Exception:
            return False

    def _init_clearcore(self):
        """
        Initialize ClearCore Board 1 via UDP for Axis E (Servo 5).
        IP: 192.168.1.171:8888
        Protocol: UDP with BOARD:1; prefix
        """
        ip = self.clearcore_config.get('ip_address', '192.168.1.171')
        port = int(self.clearcore_config.get('port', 8888))
        
        try:
            self.clearcore_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.clearcore_sock.settimeout(2.0)
            self.clearcore_ip = ip
            self.clearcore_port = port
            self.clearcore_last_position = 0
            self.clearcore_commanded_position = None
            self.clearcore_pending_target = None
            # [CHANGE 2026-03-23 16:32:24 -04:00] Optional firmware override commands for Axis E disable/stop.
            self.clearcore_disable_cmd = self._clearcore_normalize_user_cmd(
                str(self.clearcore_config.get('disable_cmd', '')).strip()
            )
            self.clearcore_stop_cmd = self._clearcore_normalize_user_cmd(
                str(self.clearcore_config.get('stop_cmd', '')).strip()
            )
            
            # Test connection
            test_msg = "BOARD:1;CMD:REQUEST_BUTTON_STATES"
            self.clearcore_sock.sendto(test_msg.encode(), (ip, port))
            
            print(f"[DEBUG] ClearCore Board 1 UDP initialized: {ip}:{port}")
            logging.info(f"ClearCore Board 1 initialized: {ip}:{port}")
        except Exception as e:
            msg = f"[ERROR] Communications Error (ClearCore): {e}"
            print(msg)
            logging.error(msg)
            self.clearcore_sock = None

    def _clearcore_normalize_user_cmd(self, user_cmd):
        """Normalize optional user override command to full BOARD:1;CMD: form."""
        if not user_cmd:
            return None
        token = str(user_cmd).strip()
        import re
        button_match = re.fullmatch(r'(?:BOARD:\d+;)?(?:CMD:)?(S\d+B\d+)\s+(START|STOP)', token, re.IGNORECASE)
        if button_match:
            button_id, action = button_match.groups()
            # [CHANGE 2026-03-24 14:02:00 -04:00] Preserve uppercase START/STOP tokens for firmware command compatibility.
            return f"BOARD:1;CMD:{button_id.upper()} {action.upper()}"
        upper = token.upper()
        if upper.startswith("BOARD:"):
            return token
        if upper.startswith("CMD:"):
            return f"BOARD:1;{token}"
        return f"BOARD:1;CMD:{token}"

    def _clearcore_get_cached_target_pulses(self):
        """Return the best cached target/current position in pulses without querying live hardware."""
        current_pulses = getattr(self, 'clearcore_pending_target', None)
        if current_pulses is None:
            commanded = getattr(self, 'clearcore_commanded_position', None)
            if commanded is not None:
                current_pulses = int(commanded)
            else:
                current_pulses = int(getattr(self, 'clearcore_last_position', 0))
        return current_pulses

    def _clearcore_build_parameters_cmd(self, position_pulses, velocity=None, accel=None):
        """Build the ClearCore parameter packet using current cached motion settings by default."""
        if velocity is None:
            velocity = getattr(self, 'clearcore_velocity', 250)
        if accel is None:
            accel = getattr(self, 'clearcore_accel', 2000)
        return f"BOARD:1;CMD:S1_Parameters:{int(velocity)},{int(accel)},{int(position_pulses)}"

    def _clearcore_translate(self, cmd):
        """Translate Galil-style commands to ClearCore Board 1 protocol for Axis E."""
        cmd = cmd.strip().upper()
        
        if cmd == "SHE" or cmd == "SH E":
            return "BOARD:1;CMD:S1B1 ENABLE"
        elif cmd == "MOE" or cmd == "MO E":
            # [CHANGE 2026-03-23 16:32:24 -04:00] Axis E disable path supports INI override, otherwise explicit unsupported.
            if getattr(self, 'clearcore_disable_cmd', None):
                return self.clearcore_disable_cmd
            return "__UNSUPPORTED__:DISABLE"
        elif cmd.startswith("PAE=") or cmd.startswith("PA E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses = int(float(match.group(1)))
                self.clearcore_last_position = pulses
                self.clearcore_commanded_position = pulses
                return self._clearcore_build_parameters_cmd(pulses)
        elif cmd.startswith("QPAE=") or cmd.startswith("QPA E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses = int(float(match.group(1)))
                self.clearcore_pending_target = pulses
                return None
        elif cmd.startswith("PRE=") or cmd.startswith("PR E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                delta_pulses = int(float(match.group(1)))
                # [CHANGE 2026-03-24 12:15:00 -04:00] Use cached/commanded baseline for relative math (avoid live REQUEST_VALUES jitter/runaway).
                current_pulses = self._clearcore_get_cached_target_pulses()
                target_pulses = current_pulses + delta_pulses
                self.clearcore_last_position = target_pulses
                self.clearcore_commanded_position = target_pulses
                return self._clearcore_build_parameters_cmd(target_pulses)
        elif cmd.startswith("QPRE=") or cmd.startswith("QPR E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                delta_pulses = int(float(match.group(1)))
                # [CHANGE 2026-03-24 12:15:00 -04:00] Use cached/commanded baseline for staged relative targets.
                current_pulses = self._clearcore_get_cached_target_pulses()
                self.clearcore_pending_target = current_pulses + delta_pulses
                return None
        elif cmd.startswith("SPE=") or cmd.startswith("SP E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses_per_sec = int(float(match.group(1)))
                self.clearcore_velocity = pulses_per_sec
                # [CHANGE 2026-03-23 13:39] Apply speed immediately using cached/pending position.
                # Avoid live REQUEST_VALUES here because it can block when controller is busy.
                current_pulses = self._clearcore_get_cached_target_pulses()
                return self._clearcore_build_parameters_cmd(current_pulses, velocity=pulses_per_sec)
        elif cmd.startswith("ACE=") or cmd.startswith("AC E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                accel = int(float(match.group(1)))
                self.clearcore_accel = accel
                # [CHANGE 2026-03-23 13:39] Apply accel immediately using cached/pending position.
                current_pulses = self._clearcore_get_cached_target_pulses()
                return self._clearcore_build_parameters_cmd(current_pulses, accel=accel)
        elif cmd.startswith("DCE=") or cmd.startswith("DC E="):
            import re
            match = re.search(r'=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                decel = int(float(match.group(1)))
                # ClearCore firmware currently has one accel parameter; mirror decel into that slot.
                self.clearcore_decel = decel
                self.clearcore_accel = decel
                # [CHANGE 2026-03-23 13:39] Apply decel(set-as-accel) immediately using cached/pending position.
                current_pulses = self._clearcore_get_cached_target_pulses()
                return self._clearcore_build_parameters_cmd(current_pulses, accel=decel)
        elif "DP" in cmd and "E" in cmd:
            return "BOARD:1;CMD:S1_ClearPosition"
        elif cmd in ("GET_BUTTON_STATES", "REQUEST_BUTTON_STATES"):
            # [CHANGE 2026-03-23 16:32:24 -04:00] Explicit query channel for Servo E HW/Soft/Effective telemetry.
            return "BOARD:1;CMD:REQUEST_BUTTON_STATES"
        elif cmd in ("MG _RPE",):
            # [CHANGE 2026-03-24 11:14:00 -04:00] Servo E position polling uses VALUES only.
            # BUTTON_STATES spam can mask/delay position-update handling and does not carry position.
            return "BOARD:1;CMD:REQUEST_VALUES"
        elif cmd in ("MG _TPE", "TP E", "TPE"):
            return "BOARD:1;CMD:REQUEST_VALUES"
        elif cmd in ("STE", "ST E"):
            # [CHANGE 2026-03-24 15:40:00 -04:00] Axis E stop: STOP plus zero-velocity latch to halt active profile execution.
            self.clearcore_pending_target = None
            stop_cmd = getattr(self, 'clearcore_stop_cmd', None) or "BOARD:1;CMD:S1B2 STOP"
            hold_pulses = self._clearcore_get_cached_target_pulses()
            zero_vel_cmd = self._clearcore_build_parameters_cmd(hold_pulses, velocity=0)
            return [stop_cmd, zero_vel_cmd]
        elif cmd in ("BGE", "BG E"):
            pending_target = getattr(self, 'clearcore_pending_target', None)
            if pending_target is None:
                return None
            self.clearcore_pending_target = None
            self.clearcore_last_position = pending_target
            self.clearcore_commanded_position = pending_target
            # [CHANGE 2026-03-24 10:28:00 -04:00] Load target/velocity before Start so Axis E uses the latest motion setpoints.
            return [
                self._clearcore_build_parameters_cmd(pending_target),
                "BOARD:1;CMD:S1B2 Start"
            ]
        
        return f"BOARD:1;CMD:{cmd}"

    def _clearcore_get_position_pulses(self):
        """Best-effort read of current Axis E position in pulses from ClearCore VALUES response."""
        original_timeout = self.clearcore_sock.gettimeout()
        try:
            self.clearcore_sock.sendto(b"BOARD:1;CMD:REQUEST_VALUES", (self.clearcore_ip, self.clearcore_port))
            self.clearcore_sock.settimeout(0.25)
            response, _ = self.clearcore_sock.recvfrom(1024)
            response_str = response.decode(errors='ignore').strip()
            if "VALUES:" in response_str:
                values = response_str.split("VALUES:", 1)[1].split(',')
                if len(values) >= 3:
                    position = int(float(values[2].strip()))
                    self.clearcore_last_position = position
                    self.clearcore_commanded_position = position
                    return position
        except Exception:
            pass
        finally:
            try:
                self.clearcore_sock.settimeout(original_timeout)
            except Exception:
                pass

        return int(getattr(self, 'clearcore_last_position', 0))

    def _clearcore_extract_position_token(self, response_text):
        """Extract Axis E actual position token from ClearCore payload variants."""
        if not isinstance(response_text, str):
            return None
        text = response_text.strip()
        if not text:
            return None
        if "VALUES:" in text:
            try:
                values = text.split("VALUES:", 1)[1].split(',')
                if len(values) >= 3:
                    return values[2].strip()
            except Exception:
                pass
        import re
        patterns = [
            r'S5P_ACT\s*=\s*([-+]?\d+(?:\.\d+)?)',
            r'S5P\s*=\s*([-+]?\d+(?:\.\d+)?)',
            r'POS(?:ITION)?\s*[:=]\s*([-+]?\d+(?:\.\d+)?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _clearcore_try_send_with_fallback(self, clearcore_cmd):
        """Send one or more ClearCore commands, tolerating unknown-command responses."""
        if not clearcore_cmd:
            return True

        candidates = clearcore_cmd if isinstance(clearcore_cmd, (list, tuple)) else [clearcore_cmd]
        original_timeout = self.clearcore_sock.gettimeout()

        try:
            for candidate in candidates:
                # [CHANGE 2026-03-24 15:22:00 -04:00] STOP burst for UDP reliability during active motion.
                upper_candidate = str(candidate).upper()
                send_repeats = 6 if 'S1B2 STOP' in upper_candidate else 1
                for attempt in range(send_repeats):
                    self.clearcore_sock.sendto(candidate.encode(), (self.clearcore_ip, self.clearcore_port))

                    # Probe briefly for immediate ERR/ACK line from firmware.
                    response_text = ""
                    try:
                        self.clearcore_sock.settimeout(0.06)
                        deadline = time.time() + 0.12
                        while time.time() < deadline:
                            response, _ = self.clearcore_sock.recvfrom(1024)
                            response_text = response.decode(errors='ignore').strip()
                            if response_text:
                                break
                    except socket.timeout:
                        response_text = ""
                    finally:
                        self.clearcore_sock.settimeout(original_timeout)

                    if response_text and "ERR:UNKNOWN COMMAND" in response_text.upper():
                        logging.warning(f"ClearCore rejected command '{candidate}': {response_text}")

                    if send_repeats > 1 and attempt < (send_repeats - 1):
                        time.sleep(0.02)
                # Continue sending any remaining commands in the sequence.

            return True
        finally:
            try:
                self.clearcore_sock.settimeout(original_timeout)
            except Exception:
                pass

        return True

    def _init_myactuator(self):
        """Initialize MyActuator motor via Waveshare CAN-to-ETH TCP connection."""
        import struct
        
        ip = self.myactuator_config.get('ip', '192.168.0.7')
        port = int(self.myactuator_config.get('port', 20001))
        motor_id = int(self.myactuator_config.get('motor_id', 1))
        
        self.myact_ip = ip
        self.myact_port = port
        self.myact_motor_id = motor_id
        self.myact_can_id = 0x140 + motor_id
        self.myact_reply_id = 0x240 + motor_id
        self.myact_zero_offset = 0.0
        
        self.MYACT_CMD_MOTOR_OFF = 0x80
        self.MYACT_CMD_MOTOR_ON = 0x88
        self.MYACT_CMD_ZERO_POSITION = 0x19
        self.MYACT_CMD_POSITION_CONTROL = 0xA4
        self.MYACT_CMD_SPEED_CONTROL = 0xA2
        self.MYACT_CMD_REQUEST_STATE = 0x9C
        
        try:
            self.myact_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.myact_sock.settimeout(5.0)
            self.myact_sock.connect((ip, port))
            print(f"[DEBUG] MyActuator connected: {ip}:{port}, Motor ID={motor_id}")
            logging.info(f"MyActuator initialized: {ip}:{port}, Motor ID={motor_id}")
        except Exception as e:
            msg = f"[ERROR] Communications Error (MyActuator): {e}"
            print(msg)
            logging.error(msg)
            self.myact_sock = None

    def send_command(self, cmd):
        """Send a command to the controller."""
        logging.info(f'SENT: {cmd}')
        try:
            query_prefixes = ('MG', 'TP', 'RP', 'QR', 'QA', 'QZ', 'QM', 'QH', 'QX')
            cmd_upper = cmd.strip().upper()
            # [CHANGE 2026-03-23 16:32:24 -04:00] Treat REQUEST_BUTTON_STATES as a query command in CommMode6.
            clearcore_query_cmds = ('GET_BUTTON_STATES', 'REQUEST_BUTTON_STATES')
            
            # [CHANGE 2026-03-22] RSI Software TCP communication (CommMode1)
            if self.mode == 'CommMode1':
                if not hasattr(self, 'rsi_sock') or self.rsi_sock is None:
                    return False

                # Lock ensures each send+recv pair is atomic across threads (polling
                # thread and GUI event loop share the same socket).  The TIM service
                # always sends a response for every command, so we always recv to
                # prevent stale responses from accumulating in the TCP buffer.
                for _attempt in range(2):
                    with self._lock:
                        try:
                            rsi_cmd = cmd.strip() + '\r\n'
                            self.rsi_sock.sendall(rsi_cmd.encode())
                            try:
                                response = self.rsi_sock.recv(1024).decode().strip()
                                logging.info(f'RECV (RSI): {response}')
                            except socket.timeout:
                                response = "0"
                            break  # success — exit retry loop
                        except OSError as _sock_err:
                            logging.warning(f'RSI socket error ({_sock_err}), reconnecting…')
                            if _attempt == 0 and self._reconnect_rsi():
                                continue  # retry once on fresh socket
                            return False
                else:
                    return False

                if cmd_upper.startswith(query_prefixes):
                    return response
                return True
            
            # ClearCore Board 1 (Axis E)
            elif self.mode == 'CommMode6':
                if not hasattr(self, 'clearcore_sock') or self.clearcore_sock is None:
                    return False
                
                clearcore_cmd = self._clearcore_translate(cmd)
                if isinstance(clearcore_cmd, str) and clearcore_cmd.startswith("__UNSUPPORTED__"):
                    return "UNSUPPORTED"
                is_clearcore_query = cmd_upper.startswith(query_prefixes) or cmd_upper in clearcore_query_cmds
                if not is_clearcore_query:
                    return self._clearcore_try_send_with_fallback(clearcore_cmd)

                if not clearcore_cmd:
                    return True

                if is_clearcore_query:
                    try:
                        # [CHANGE 2026-03-24 16:14:00 -04:00] Read a short burst of packets; position may arrive after first UDP frame.
                        original_timeout = self.clearcore_sock.gettimeout()
                        latest_text = ""
                        latest_values_text = ""
                        best_position = None

                        query_cmds = clearcore_cmd if isinstance(clearcore_cmd, (list, tuple)) else [clearcore_cmd]
                        for query_cmd in query_cmds:
                            self.clearcore_sock.sendto(query_cmd.encode(), (self.clearcore_ip, self.clearcore_port))
                            self.clearcore_sock.settimeout(0.06)
                            deadline = time.time() + 0.18

                            while time.time() < deadline:
                                try:
                                    response, addr = self.clearcore_sock.recvfrom(1024)
                                except socket.timeout:
                                    continue
                                response_str = response.decode(errors='ignore').strip()
                                if response_str:
                                    latest_text = response_str
                                    if 'VALUES:' in response_str.upper():
                                        latest_values_text = response_str
                                    extracted = self._clearcore_extract_position_token(response_str)
                                    if extracted is not None:
                                        best_position = extracted

                        self.clearcore_sock.settimeout(original_timeout)

                        if best_position is not None:
                            try:
                                parsed_pos = int(float(str(best_position).strip()))
                                self.clearcore_last_position = parsed_pos
                                self.clearcore_commanded_position = parsed_pos
                            except Exception:
                                pass

                        # [CHANGE 2026-03-24 10:44:00 -04:00] Prefer VALUES payload because it carries live velocity/position.
                        if latest_values_text:
                            logging.info(f'RECV (ClearCore): {latest_values_text}')
                            return latest_values_text

                        # Fall back to any last payload when VALUES is unavailable.
                        if latest_text:
                            logging.info(f'RECV (ClearCore): {latest_text}')
                            return latest_text

                        if best_position is not None:
                            logging.info(f'RECV (ClearCore): {best_position}')
                            return str(best_position)
                        return "0"
                    except socket.timeout:
                        return "0"
                    finally:
                        try:
                            self.clearcore_sock.settimeout(original_timeout)
                        except Exception:
                            pass
                
                return True
            
            # MyActuator (Axis H)
            elif self.mode == 'CommMode5':
                if not hasattr(self, '_myact_send_command'):
                    if not getattr(self, '_missing_myactuator_handler_logged', False):
                        logging.error('CommMode5 unavailable: _myact_send_command is not implemented on ControllerComm')
                        self._missing_myactuator_handler_logged = True
                    return False
                return self._myact_send_command(cmd)
            
            else:
                raise ValueError(f"Unknown mode: {self.mode}")
        
        except Exception as e:
            print(f"Communications Error: {e}")
            return False

    def close(self):
        """Cleanly close the communications channel."""
        if self.mode == 'CommMode1':
            if hasattr(self, 'rsi_sock') and self.rsi_sock:
                self.rsi_sock.close()
        elif self.mode == 'CommMode6':
            if hasattr(self, 'clearcore_sock') and self.clearcore_sock:
                self.clearcore_sock.close()
        elif self.mode == 'CommMode5':
            if hasattr(self, 'myact_sock') and self.myact_sock:
                self.myact_sock.close()

    # ... (keep all existing MyActuator methods unchanged)