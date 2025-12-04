
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
        if not port:
            msg = "Communications Error (Serial): serial_config must include 'port' for CommMode2."
            print(msg)
            logging.error(msg)
            self.ser = None
            return
        try:
            self.ser = serial.Serial(port=port, baudrate=baudrate, timeout=timeout)
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
    def __init__(self, mode='udp', udp_config=None, serial_config=None, galil_config=None):
        """
        Initialize the ControllerComm class for either UDP (Ethernet) or Serial communication.
        Args:
            mode (str): 'udp' for ClearCore, 'serial' for Galil DMC-4080
            udp_config (dict): UDP configuration (IP addresses, ports)
            serial_config (dict): Serial configuration (port, baudrate, timeout)
        """
        self.mode = mode if mode in ['CommMode1', 'CommMode2', 'CommMode3'] else 'CommMode3'
        self.udp_config = udp_config or {}
        self.serial_config = serial_config or {}
        self.message_queue = queue.Queue()  # Thread-safe queue for incoming messages
        self.galil_config = galil_config or {}
        if self.mode == 'CommMode3':
            self._init_udp()
        elif self.mode == 'CommMode2':
            self._init_serial()
        elif self.mode == 'CommMode1':
            self._init_galil_eth()

    def _init_galil_eth(self):
        """
        Initialize Galil Ethernet (gclib) connection.
        """
        try:
            import gclib # pyright: ignore[reportMissingImports]
        except ImportError:
            raise ImportError("gclib package is required for Galil Ethernet mode.")
        self.gclib = gclib.py()
        address = self.galil_config.get('address') if hasattr(self, 'galil_config') else None
        if not address:
            raise ValueError("galil_config must include 'address' for galil_eth mode.")
        try:
            self.gclib.GOpen(f"{address} --direct -s ALL")
        except Exception as e:
            print(f"Communications Error (Galil Ethernet): {e}")
            self.gclib = None

    def _init_udp(self):
        """
        Initialize UDP socket and start background receiver thread for ClearCore communication.
        """
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_port = self.udp_config.get('local_port', 8889)
        self.udp_sock.bind(('', bind_port))

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
            if self.mode == 'CommMode3':
                ip = self.udp_config.get('ip1')
                port = self.udp_config.get('port1')
                if not ip or not port:
                    raise ValueError("UDP config missing IP or port.")
                self.udp_sock.sendto(cmd.encode('utf-8'), (ip, port))
                return True
            elif self.mode == 'CommMode2':
                if self.ser:
                    self.ser.write((cmd + '\r').encode('utf-8'))
                    # Force logging and debug queue for all commands
                    logging.info(f'SENT: {cmd} [serial]')
                    self.message_queue.put(f'SENT: {cmd}')
                    return True
                else:
                    print("Communications Error: Serial port not open, cannot send command.")
                    return False
            elif self.mode == 'CommMode1':
                if not hasattr(self, 'gclib'):
                    raise RuntimeError("Galil Ethernet (gclib) not initialized.")
                # If command is a query, return the response string
                query_prefixes = ('MG', 'TP', 'RP', 'QR', 'QA', 'QZ', 'QM', 'QH', 'QX')
                if cmd.strip().upper().startswith(query_prefixes):
                    response = self.gclib.GCommand(cmd)
                    logging.info(f'RECV: {response}')
                    return response
                else:
                    response = self.gclib.GCommand(cmd)
                    logging.info(f'RECV: {response}')
                    self.message_queue.put(response)
                    return True
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
        Cleanly close the communications channel (socket, serial port, or gclib connection).
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
