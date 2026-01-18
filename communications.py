
import logging
logging.basicConfig(filename='controller_comm.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')

"""
================================================================================
CONTROLLER COMMUNICATIONS MODULE - REVISION 1.1
Unified Interface for Galil DMC-4080 & ClearCore (Configurable Modes)
================================================================================

PURPOSE:
Provides a modular, unified interface for sending and receiving commands to industrial servo controllers:
- CommMode1: Galil DMC-4080 via Ethernet (gclib)
- CommMode2: Galil DMC-4080 via Serial (RS232/USB)
- CommMode3: Teknic ClearCore via UDP
Designed for easy integration with GUI/control programs, hardware abstraction, and future extensibility.

MODES:
- mode='CommMode1': Galil Ethernet (gclib)
- mode='CommMode2': Galil Serial (RS232/USB)
- mode='CommMode3': ClearCore UDP
- mode='CommMode4': RMP (RapidCode Motion Platform)

USAGE PATTERNS:
# --- CommMode3 (ClearCore UDP) Example ---
udp_config = {
    'ip1': '192.168.1.151', 'port1': 8888,  # ClearCore Controller
    'local_port': 8889
}
comm = ControllerComm(mode='CommMode3', udp_config=udp_config)
comm.send_command('CMD:REQUEST_BUTTON_STATES')
response = comm.receive_response(timeout=2.0)
comm.close()

# --- CommMode2 (Galil Serial) Example ---
serial_config = {
    'port': 'COM3', 'baudrate': 115200, 'timeout': 0.1
}
comm = ControllerComm(mode='CommMode2', serial_config=serial_config)
comm.send_command('TPA')  # Example Galil command
response = comm.receive_response(timeout=2.0)
comm.close()

# --- CommMode1 (Galil Ethernet/gclib) Example ---
galil_config = {
    'address': '192.168.1.2'  # Replace with your Galil's IP
}
comm = ControllerComm(mode='CommMode1', galil_config=galil_config)
comm.send_command('TPA')  # Example Galil command
response = comm.receive_response(timeout=2.0)
comm.close()

# --- CommMode4 (RMP / RapidCode) Example ---
rmp_config = {
    'use_hardware': False,  # True for real hardware, False for phantom axes
    'num_axes': 8
}
comm = ControllerComm(mode='CommMode4', rmp_config=rmp_config)
# RMP controller accessed via comm.rmp
# comm.rmp.move_absolute(0, 45.0)
# positions = comm.rmp.get_positions()
comm.close()
response = comm.receive_response(timeout=2.0)
comm.close()

AUTHOR: Greg Skovira
VERSION: 1.1.0
DATE: December 2, 2025
LICENSE: Internal Use Only

================================================================================
CLASSES AND FUNCTIONS INVENTORY
================================================================================


CLASSES:
ControllerComm - Unified communications class for Galil (CommMode1: Ethernet/gclib, CommMode2: Serial) and ClearCore (CommMode3: UDP)
                Handles initialization, command sending, and background message reception

import logging

# Set up logging to file
logging.basicConfig(filename='controller_comm.log',
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')
CORE COMMUNICATION FUNCTIONS:
__init__()         - Initialize communications (selects CommMode1, CommMode2, or CommMode3)
send_command()     - Send command to specified controller (mode-specific)
receive_response() - Retrieve next message from controller (thread-safe)
close()            - Cleanly close communications (socket, serial port, or gclib connection)
_init_udp()        - Internal: Initialize UDP socket and receiver thread
_udp_receiver()    - Internal: Background thread for UDP message reception
_init_serial()     - Internal: Initialize serial port and receiver thread
_serial_receiver() - Internal: Background thread for serial message reception
_init_galil_eth()  - Internal: Initialize Galil Ethernet (gclib) connection

================================================================================
REVISION HISTORY
================================================================================

Rev 1.2.0 - January 15, 2026 - Add MyActuator motor support (CommMode5)
    - Added mode='CommMode5' for MyActuator motors via Waveshare CAN-to-ETH converter
    - Implemented CAN frame encoding/decoding for Waveshare TCP protocol
    - Added Galil-to-MyActuator command translation (SH, MO, PA, BG, TP, DP, SP)
    - Support for position control with speed limits (0xA4 command)
    - Automatic angle wrapping for ±180° single-turn encoder
    - MyActuator-specific helper methods for CAN communication

Rev 1.1.0 - December 2, 2025 - Add Galil Ethernet (gclib) support
    - Added mode='galil_eth' for Galil DMC-4080 Ethernet communication using gclib
    - Updated usage patterns and documentation

Rev 1.0.0 - December 2, 2025 - Initial release
    - Unified communications class for Galil (serial) and ClearCore (UDP)
    - Threaded background receiver and message queue
    - Modular design for easy integration
    - Comprehensive header and documentation

================================================================================
"""
import socket
import queue
import threading

logging.info('ControllerComm module loaded. Logging initialized.')
class ControllerComm:
    def _init_serial(self):
        """
        Initialize Galil Serial (RS232/USB) connection and start receiver thread.
        """
        try:
            import serial # pyright: ignore[reportMissingImports]
        except ImportError:
            msg = "Communications Error (Serial): pyserial package is required for Galil Serial mode."
            print(msg)
            logging.error(msg)
            self.ser = None
            return
        port = self.serial_config.get('port')
        baudrate = self.serial_config.get('baudrate', 115200)
        timeout = self.serial_config.get('timeout', 0.1)
        # Explicitly set parity, stopbits, and rtscts for Galil compatibility
        parity = self.serial_config.get('parity', 'N')  # None/Even/Odd
        stopbits = self.serial_config.get('stopbits', 1)
        rtscts = self.serial_config.get('rtscts', False)
        if not port:
            msg = "Communications Error (Serial): serial_config must include 'port' for CommMode2."
            print(msg)
            logging.error(msg)
            self.ser = None
            return
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                parity=parity,
                stopbits=stopbits,
                rtscts=rtscts
            )
        except Exception as e:
            msg = f"Communications Error (Serial): {e}"
            print(msg)
            logging.error(msg)
            self.ser = None
            return
        import threading
        self._serial_receiver_running = True
        self.serial_thread = threading.Thread(target=self._serial_receiver, daemon=True)
        self.serial_thread.start()
        logging.info(f"Serial receiver thread started on port {port}")

    def _serial_receiver(self):
        """
        Background thread to receive messages from Galil Serial and put them in the queue.
        """
        if not self.ser:
            msg = "Serial receiver thread exiting: serial port not open."
            print(msg)
            logging.info(msg)
            return
        while getattr(self, '_serial_receiver_running', True):
            if self.ser is None or not self.ser.is_open:
                msg = "Serial receiver thread exiting: serial port closed or lost."
                print(msg)
                logging.info(msg)
                break
            try:
                if self.ser.in_waiting:
                    data = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if data:
                        self.message_queue.put(data)
            except Exception as e:
                # Only print error if not shutting down
                if getattr(self, '_serial_receiver_running', True):
                    msg = f"Communications Error (Serial Receiver): {e}"
                    print(msg)
                    logging.error(msg)
                break
    def __init__(self, mode='udp', udp_config=None, serial_config=None, galil_config=None, rmp_config=None, myactuator_config=None):
        """
        Initialize the ControllerComm class for either UDP (Ethernet) or Serial communication.
        Args:
            mode (str): 'CommMode1' for Galil Ethernet, 'CommMode2' for Galil Serial,
                       'CommMode3' for ClearCore UDP, 'CommMode4' for RMP, 'CommMode5' for MyActuator
            udp_config (dict): UDP configuration (IP addresses, ports)
            serial_config (dict): Serial configuration (port, baudrate, timeout)
            galil_config (dict): Galil Ethernet configuration (address)
            rmp_config (dict): RMP configuration (use_hardware, num_axes)
            myactuator_config (dict): MyActuator configuration (ip, port, motor_id)
        """
        self.mode = mode if mode in ['CommMode1', 'CommMode2', 'CommMode3', 'CommMode4', 'CommMode5'] else 'CommMode3'
        self.udp_config = udp_config or {}
        self.serial_config = serial_config or {}
        self.galil_config = galil_config or {}
        self.rmp_config = rmp_config or {}
        self.myactuator_config = myactuator_config or {}
        self.message_queue = queue.Queue()  # Thread-safe queue for incoming messages
        self._lock = threading.Lock()
        
        if self.mode == 'CommMode3':
            self._init_udp()
        elif self.mode == 'CommMode2':
            self._init_serial()
        elif self.mode == 'CommMode1':
            self._init_galil_eth()
        elif self.mode == 'CommMode4':
            self._init_rmp()
        elif self.mode == 'CommMode5':
            self._init_myactuator()

    def _init_galil_eth(self):
        """
        Initialize Galil Ethernet (gclib) connection with detailed error reporting.
        """
        try:
            import gclib # pyright: ignore[reportMissingImports]
        except ImportError:
            print("[ERROR] gclib package is not installed. Run 'pip install gclib' in your environment.")
            self.gclib = None
            return
        self.gclib = gclib.py()
        address = self.galil_config.get('address') if hasattr(self, 'galil_config') else None
        if not address:
            print("[ERROR] galil_config must include 'address' for galil_eth mode.")
            self.gclib = None
            return
        try:
            print(f"[DEBUG] Attempting GOpen to address: {address}")
            self.gclib.GOpen(f"{address} --direct -s ALL")
            print("[DEBUG] Galil Ethernet (gclib) connection established.")
        except Exception as e:
            print(f"[ERROR] Communications Error (Galil Ethernet): {e}")
            self.gclib = None

    def _init_rmp(self):
        """
        Initialize RMP (RapidCode) controller with phantom axes or hardware.
        """
        try:
            from rmp_controller import RMPController
        except ImportError:
            msg = "[ERROR] rmp_controller module not found. Ensure rmp_controller.py is in the same directory."
            print(msg)
            logging.error(msg)
            self.rmp = None
            return
        
        use_hardware = self.rmp_config.get('use_hardware', False)
        num_axes = self.rmp_config.get('num_axes', 8)
        
        try:
            self.rmp = RMPController(use_hardware=use_hardware, num_axes=num_axes)
            
            if self.rmp.connect():
                print(f"[DEBUG] RMP controller initialized: {num_axes} axes, hardware={use_hardware}")
                logging.info(f"RMP initialized: {num_axes} axes, hardware={use_hardware}")
            else:
                msg = "[ERROR] RMP controller failed to connect."
                print(msg)
                logging.error(msg)
                self.rmp = None
        except Exception as e:
            msg = f"[ERROR] Communications Error (RMP): {e}"
            print(msg)
            logging.error(msg)
            self.rmp = None

    def _init_udp(self):
        """
        Initialize UDP socket and start background receiver thread for ClearCore communication.
        """
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_port = self.udp_config.get('local_port', 8889)
        self.udp_sock.bind(('', bind_port))

    def _init_myactuator(self):
        """
        Initialize MyActuator motor via Waveshare CAN-to-ETH TCP connection.
        """
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
        
        # MyActuator protocol commands
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
    
    def _myact_create_can_frame(self, can_id, data):
        """Create Waveshare CAN frame: DLC + CAN_ID (big endian) + Data"""
        import struct
        dlc = len(data)
        return struct.pack('B', dlc) + struct.pack('>I', can_id) + data + b'\x00' * (8 - dlc)
    
    def _myact_send_can(self, can_id, data):
        """Send CAN message via Waveshare"""
        if not hasattr(self, 'myact_sock') or self.myact_sock is None:
            return False
        frame = self._myact_create_can_frame(can_id, data)
        self.myact_sock.send(frame)
        return True
    
    def _myact_receive_can(self, timeout=1.0):
        """Receive CAN message from Waveshare"""
        import struct
        if not hasattr(self, 'myact_sock') or self.myact_sock is None:
            return None, None
        self.myact_sock.settimeout(timeout)
        try:
            data = self.myact_sock.recv(1024)
            if len(data) >= 13:
                dlc = data[0] & 0x0F
                can_id = struct.unpack('>I', data[1:5])[0]
                payload = data[5:5+dlc]
                return can_id, payload
        except socket.timeout:
            pass
        return None, None
    
    def _myact_wrap_angle(self, angle):
        """Wrap angle to ±180° range"""
        while angle > 180.0:
            angle -= 360.0
        while angle < -180.0:
            angle += 360.0
        return angle
    
    def _myact_send_command(self, cmd):
        """
        Translate Galil-like commands to MyActuator CAN protocol.
        Supported commands:
          SH H - Enable motor (servo here)
          MO H - Disable motor (motor off)
          PA H=<degrees> - Position absolute
          BG H - Begin motion
          TP H - Tell position (returns current position)
          DP H=0 - Define position (zero)
          JG H=<speed>;BG H - Jog (continuous speed)
          ST H - Stop
        """
        import struct
        
        cmd = cmd.strip().upper()
        # print(f"[DEBUG _myact_send_command] Processing: '{cmd}'")  # Commented to reduce console noise
        
        # Handle compound commands (split on semicolon)
        if ';' in cmd:
            # print(f"[DEBUG _myact_send_command] Splitting compound command: {cmd}")
            parts = cmd.split(';')
            results = []
            for part in parts:
                # print(f"[DEBUG _myact_send_command] Processing part: '{part.strip()}'")
                result = self._myact_send_command(part.strip())
                # print(f"[DEBUG _myact_send_command] Part '{part.strip()}' returned: {result}")
                results.append(result)
            # Return True if any part succeeded
            final_result = any(results)
            # print(f"[DEBUG _myact_send_command] Compound command final result: {final_result}")
            return final_result
        
        # Enable motor: SH H or SHH
        if cmd in ('SH H', 'SH', 'SHH'):
            data = bytes([self.MYACT_CMD_MOTOR_ON, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            self._myact_receive_can(timeout=0.5)
            self.myact_enabled = True
            print(f"[DEBUG MyActuator] Enable motor command sent, motor enabled")
            return True
        
        # Disable motor: MO H or MOH
        elif cmd in ('MO H', 'MO', 'MOH'):
            data = bytes([self.MYACT_CMD_MOTOR_OFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            self._myact_receive_can(timeout=0.5)
            self.myact_enabled = False
            print(f"[DEBUG MyActuator] Disable motor command sent, motor disabled (motion blocked)")
            return True
        
        # Zero position: DP H=0 or DPH=0
        elif 'DP' in cmd and 'H' in cmd:
            # Query current position to use as new zero offset
            data = bytes([self.MYACT_CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            can_id, response = self._myact_receive_can(timeout=0.5)
            
            if response and len(response) >= 8:
                # Get current absolute position
                position_raw = struct.unpack('<h', response[6:8])[0]
                current_abs_position = position_raw * 0.01
                
                # DO NOT send 0x19 command - it actually zeros the motor's encoder
                # Just update our software offset
                self.myact_zero_offset = current_abs_position
                
                print(f"[DEBUG MyActuator] Zero position set: current absolute position {current_abs_position:.2f}° is now 0.0°")
            else:
                print(f"[DEBUG MyActuator] Zero position failed: could not read current position")
            return True
        
        # Tell position: TP H, MG _TPH, or MG _RPH (reference position)
        elif cmd in ('TP H', 'TP', 'MG _TPH', 'MG _RPH'):
            data = bytes([self.MYACT_CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            can_id, response = self._myact_receive_can(timeout=0.5)
            if response and len(response) >= 8:
                position_raw = struct.unpack('<h', response[6:8])[0]
                position_abs = position_raw * 0.01
                position = position_abs - self.myact_zero_offset
                # Return position in pulses (like Galil does) for consistency
                position_pulses = position * 100.0  # 100 pulses per degree for axis H
                return str(position_pulses)
            return "0.0"
        
        # Position absolute: PAH=<value>
        elif 'PA' in cmd and 'H' in cmd:
            # Extract position value (in pulses from GUI)
            import re
            match = re.search(r'H\s*=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses = float(match.group(1))
                # Convert pulses to degrees using axis H scaling (100 pulses/degree)
                target_deg = pulses / 100.0
                # Store for BG command
                self.myact_pending_position = target_deg
                print(f"[DEBUG MyActuator] PA command: {pulses} pulses = {target_deg}°")
                return True
        
        # Position relative: PRH=<value>
        elif 'PR' in cmd and 'H' in cmd:
            print(f"[DEBUG MyActuator] PR command detected: {cmd}")
            # Extract relative position value (in pulses from GUI)
            import re
            match = re.search(r'H\s*=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses = float(match.group(1))
                # Convert pulses to degrees
                relative_deg = pulses / 100.0
                print(f"[DEBUG MyActuator] PR: Input {pulses} pulses = {relative_deg:+.2f}° relative move")
                
                # Use pending position if available, otherwise query current position
                # This matches Galil behavior: PR is relative to commanded position, not actual encoder
                if hasattr(self, 'myact_pending_position') and self.myact_pending_position is not None:
                    current_pos = self.myact_pending_position
                    print(f"[DEBUG MyActuator] PR: Using pending position {current_pos:.2f}° as reference")
                else:
                    # Get actual position if no pending move
                    data = bytes([self.MYACT_CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    self._myact_send_can(self.myact_can_id, data)
                    can_id, response = self._myact_receive_can(timeout=0.5)
                    if response and len(response) >= 8:
                        position_raw = struct.unpack('<h', response[6:8])[0]
                        position_abs = position_raw * 0.01
                        current_pos = position_abs - self.myact_zero_offset
                        print(f"[DEBUG MyActuator] PR: Using actual position {current_pos:.2f}° as reference")
                    else:
                        print(f"[DEBUG MyActuator] PR command failed: could not read current position")
                        return False
                
                # Calculate new target
                target_deg = current_pos + relative_deg
                self.myact_pending_position = target_deg
                print(f"[DEBUG MyActuator] PR calculation: current={current_pos:.2f}° + relative={relative_deg:+.2f}° → target={target_deg:.2f}°")
                return True
            else:
                print(f"[DEBUG MyActuator] PR regex match failed for: {cmd}")
                return False
        
        # Begin motion: BGH
        elif cmd in ('BG H', 'BG', 'BGH'):
            # Check if motor is enabled
            if not getattr(self, 'myact_enabled', False):
                print(f"[DEBUG MyActuator] BG command blocked - motor is disabled")
                return False
            
            if hasattr(self, 'myact_pending_position'):
                position_deg = self.myact_pending_position
                # Get speed from stored value or use default
                max_speed = getattr(self, 'myact_pending_speed', 100.0)
                
                print(f"[DEBUG MyActuator] BG command: Moving to {position_deg}° at {max_speed} dps")
                
                # Execute position move
                absolute_position = position_deg + self.myact_zero_offset
                wrapped_position = self._myact_wrap_angle(absolute_position)
                position_counts = int(wrapped_position * 100)
                speed_counts = int(max_speed)
                
                print(f"[DEBUG MyActuator] Sending: position={wrapped_position:.2f}° ({position_counts} counts), speed={speed_counts} dps")
                
                # Pack: CMD + NULL + speed(2) + position(4)
                data = struct.pack('<BHi', 0x00, speed_counts, position_counts)
                data = bytes([self.MYACT_CMD_POSITION_CONTROL]) + data
                
                print(f"[DEBUG MyActuator] CAN frame: {data.hex()}")
                
                self._myact_send_can(self.myact_can_id, data)
                self._myact_receive_can(timeout=0.5)
                return True
            else:
                print(f"[DEBUG MyActuator] BG command failed: no pending position or jog")
                return False
        
        # Speed: SP H=<value>
        elif 'SP' in cmd and 'H' in cmd:
            import re
            match = re.search(r'H\s*=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses_per_sec = float(match.group(1))
                # Convert pulses/sec to degrees/sec using axis H scaling (100 pulses/degree)
                speed_val = pulses_per_sec / 100.0
                self.myact_pending_speed = speed_val
                print(f"[DEBUG MyActuator] SP command: {pulses_per_sec} pps = {speed_val} dps")
                return True
        
        # Jog (continuous speed): JGH=<value>;BGH
        # MyActuator doesn't support speed mode, so jog using large position target instead
        elif 'JG' in cmd and 'H' in cmd:
            print(f"[DEBUG MyActuator] JG command detected: {cmd}")
            import re
            match = re.search(r'H\s*=\s*([-+]?\d+\.?\d*)', cmd)
            if match:
                pulses_per_sec = float(match.group(1))
                # Convert pulses/sec to degrees/sec
                speed_dps = abs(pulses_per_sec / 100.0)
                
                # Get current position to calculate target
                data = bytes([self.MYACT_CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                self._myact_send_can(self.myact_can_id, data)
                can_id, response = self._myact_receive_can(timeout=0.5)
                
                if response and len(response) >= 8:
                    position_raw = struct.unpack('<h', response[6:8])[0]
                    current_abs = position_raw * 0.01
                    current_pos = current_abs - self.myact_zero_offset
                    
                    # Use direction to target a position well away from wrap boundaries
                    # Using ±170° instead of ±180° to avoid wrap issues with encoder offset
                    if pulses_per_sec > 0:
                        # Jog CW - go to positive limit (well inside range)
                        target_deg = 170.0
                    else:
                        # Jog CCW - go to negative limit (well inside range)
                        target_deg = -170.0
                else:
                    # Fallback if can't read position
                    target_deg = 180.0 if pulses_per_sec > 0 else -180.0
                
                print(f"[DEBUG MyActuator] JG command: {pulses_per_sec} pps = jogging to {target_deg:.1f}° at {speed_dps} dps (current={current_pos:.2f}°)")
                
                # Store for BG command
                self.myact_pending_position = target_deg
                self.myact_pending_speed = speed_dps
                self.myact_jog_active = True
                return True
            else:
                print(f"[DEBUG MyActuator] JG regex match failed for: {cmd}")
                return False
        
        # Stop command: STH
        elif 'ST' in cmd and 'H' in cmd:
            print(f"[DEBUG MyActuator] Stop command detected: {cmd}")
            
            # For MyActuator, stop means: temporarily disable to halt motion, then re-enable to hold position
            # (Disable button will send MOH afterwards to fully disable if needed)
            data = bytes([self.MYACT_CMD_MOTOR_OFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            self._myact_receive_can(timeout=0.1)
            
            # Small delay
            import time
            time.sleep(0.05)
            
            # Re-enable to hold position
            data = bytes([self.MYACT_CMD_MOTOR_ON, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            self._myact_send_can(self.myact_can_id, data)
            self._myact_receive_can(timeout=0.1)
            
            print(f"[DEBUG MyActuator] Motor stopped and holding position")
            
            # Clear jog active flag
            self.myact_jog_active = False
            return True
        
        # print(f"[DEBUG MyActuator] No match for command: {cmd}")  # Commented to reduce console noise
        return False

    def send_command(self, cmd):
        """
        Send a command to the controller.
        Args:
            cmd (str): Command string to send.
        Returns:
            For query commands (MG, TP, etc.) in CommMode1, returns the response string.
            For other commands, returns True/False for success.
        """
        logging.info(f'SENT: {cmd}')
        try:
            query_prefixes = ('MG', 'TP', 'RP', 'QR', 'QA', 'QZ', 'QM', 'QH', 'QX')
            if self.mode == 'CommMode3':
                ip = self.udp_config.get('ip1')
                port = self.udp_config.get('port1')
                if not ip or not port:
                    raise ValueError("UDP config missing IP or port.")
                self.udp_sock.sendto(cmd.encode('utf-8'), (ip, port))
                return True
            elif self.mode == 'CommMode2':
                if self.ser:
                    # Flush buffers before sending
                    self.ser.reset_input_buffer()
                    self.ser.reset_output_buffer()
                    self.ser.write((cmd + '\r').encode('utf-8'))
                    logging.info(f'SENT: {cmd} [serial]')
                    # For query commands, wait for and return all responses
                    if cmd.strip().upper().startswith(query_prefixes):
                        responses = []
                        self.ser.timeout = 2.0
                        while True:
                            line = self.ser.readline()
                            if not line:
                                break
                            responses.append(line.decode(errors='replace').strip())
                        return '\n'.join(responses)
                    self.message_queue.put(f'SENT: {cmd}')
                    return True
                else:
                    print("Communications Error: Serial port not open, cannot send command.")
                    return False
            elif self.mode == 'CommMode1':
                if not hasattr(self, 'gclib') or self.gclib is None:
                    # Silently return False instead of printing error on every poll
                    return False
                # If command is a query, return the response string
                query_prefixes = ('MG', 'TP', 'RP', 'QR', 'QA', 'QZ', 'QM', 'QH', 'QX')
                # Serialize access to gclib to avoid concurrent reads
                with self._lock:
                    if cmd.strip().upper().startswith(query_prefixes):
                        response = self.gclib.GCommand(cmd)
                        logging.info(f'RECV: {response}')
                        return response
                    else:
                        response = self.gclib.GCommand(cmd)
                        logging.info(f'RECV: {response}')
                        if response is not None and str(response).strip() == '?':
                            print(f"Communications Error: question mark returned by controller for '{cmd}'")
                            logging.error(f"RECV '?': cmd={cmd}")
                            return False
                        self.message_queue.put(response)
                        return True
            elif self.mode == 'CommMode5':
                # MyActuator motor commands - translate Galil-like syntax to CAN
                # print(f"[DEBUG CommMode5] Received command: {cmd}")  # Commented to reduce console noise
                return self._myact_send_command(cmd)
            else:
                raise ValueError(f"Unknown mode: {self.mode}")
        except Exception as e:
            print(f"Communications Error: {e}")
            return False

    def receive_response(self, timeout=1.0) -> str | None:
        """
        Retrieve the next message from the controller (thread-safe).
        Args:
            timeout (float): Seconds to wait for a message before returning None
        Returns:
            str or None: Received message or None if timeout
        """
        try:
            msg = self.message_queue.get(timeout=timeout)
            logging.info(f'RECV: {msg}')
            return msg
        except queue.Empty:
            return None

    def close(self):
        """
        Cleanly close the communications channel (socket, serial port, gclib, RMP, or MyActuator connection).
        """
        if self.mode == 'CommMode3':
            self.udp_sock.close()
        elif self.mode == 'CommMode2':
            # Signal the receiver thread to exit before closing the port
            self._serial_receiver_running = False
            if hasattr(self, 'serial_thread') and self.serial_thread.is_alive():
                import time
                time.sleep(0.1)  # Give the thread a moment to exit
            if self.ser:
                self.ser.close()
            else:
                print("Communications Error: Serial port not open, nothing to close.")
        elif self.mode == 'CommMode1':
            if hasattr(self, 'gclib'):
                self.gclib.GClose()
        elif self.mode == 'CommMode4':
            if hasattr(self, 'rmp') and self.rmp:
                self.rmp.disconnect()
        elif self.mode == 'CommMode5':
            if hasattr(self, 'myact_sock') and self.myact_sock:
                self.myact_sock.close()
