"""
TIM ClearCore Adapter - Axis E (Steering/Address Angle)
========================================================

Translates Galil-like commands into ClearCore UDP messages for axis E.
Axis E is a non-coordinated auxiliary axis (ClearCore + Teknic servo).

Protocol: UDP to 192.168.1.171:8888 with BOARD:1;CMD: prefix
"""

import logging
import socket
import re

logger = logging.getLogger(__name__)


class ClearCoreAdapter:
    """Adapter for ClearCore control of axis E (steering/address angle)."""
    
    def __init__(self, config=None, phantom_mode=False, watchdog=None):
        """
        Initialize ClearCore adapter.
        
        Args:
            config: Configuration dict with ClearCore IP/port
            phantom_mode: If True, use mock UDP (no hardware)
            watchdog: SafetyWatchdog instance
        """
        self.config = config or {}
        self.phantom_mode = phantom_mode
        self.watchdog = watchdog
        self.socket = None
        self.clearcore_ip = config.get('ip_address', '192.168.1.171')
        self.clearcore_port = config.get('port', 8888)
        self.last_position = 0
        self.commanded_position = 0
        
        if not phantom_mode:
            self._init_clearcore()
        else:
            logger.info("ClearCore adapter in PHANTOM MODE (mock)")
    
    def _init_clearcore(self):
        """Initialize UDP socket for ClearCore communication."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(2.0)
            logger.info(f"ClearCore UDP initialized for {self.clearcore_ip}:{self.clearcore_port}")
        except Exception as e:
            logger.error(f"Failed to initialize ClearCore socket: {e}")
            self.socket = None
    
    def handle_command(self, command, axis):
        """
        Handle a Galil-like command for axis E (ClearCore).
        
        Args:
            command: Full command string (e.g., "PA E=45")
            axis: Axis letter ('E')
        
        Returns:
            Response string (numeric value or status)
        """
        try:
            cmd_upper = command.strip().upper()
            
            if cmd_upper.startswith('SH') or cmd_upper.startswith('SHE'):
                return self._handle_enable()
            elif cmd_upper.startswith('MO') or cmd_upper.startswith('MOE'):
                return self._handle_disable()
            elif cmd_upper.startswith('PA') or cmd_upper.startswith('PAE'):
                value = self._extract_numeric(cmd_upper)
                return self._handle_absolute_move(value)
            elif cmd_upper.startswith('PR') or cmd_upper.startswith('PRE'):
                value = self._extract_numeric(cmd_upper)
                return self._handle_relative_move(value)
            elif cmd_upper.startswith('SP') or cmd_upper.startswith('SPE'):
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_speed(value)
            elif cmd_upper.startswith('AC') or cmd_upper.startswith('ACE'):
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_accel(value)
            elif cmd_upper.startswith('DC') or cmd_upper.startswith('DCE'):
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_decel(value)
            elif cmd_upper.startswith('DP') or cmd_upper.startswith('DPE'):
                return self._handle_clear_position()
            elif 'MG _RP' in cmd_upper or 'MG _TP' in cmd_upper or 'REQUEST_VALUES' in cmd_upper:
                return self._handle_query_position()
            elif 'MG _MO' in cmd_upper or 'REQUEST_BUTTON_STATES' in cmd_upper:
                return self._handle_query_status()
            elif 'MG _SP' in cmd_upper:
                return self._handle_query_speed()
            elif cmd_upper.startswith('ST') or cmd_upper.startswith('STE'):
                return self._handle_stop()
            else:
                logger.warning(f"Unknown ClearCore command: {command}")
                return "0"
        
        except Exception as e:
            logger.error(f"Error handling ClearCore command '{command}': {e}")
            return "0"
    
    def _extract_numeric(self, command):
        """Extract numeric value from command (e.g., '45' from 'PA E=45')."""
        match = re.search(r'=\s*([-+]?\d+\.?\d*)', command)
        if match:
            return float(match.group(1))
        return 0.0
    
    def _send_clearcore_cmd(self, cmd_payload):
        """Send command to ClearCore board via UDP."""
        if self.phantom_mode:
            logger.debug(f"[phantom] ClearCore: {cmd_payload}")
            return True
        
        if not self.socket:
            logger.warning("ClearCore socket not initialized")
            return False
        
        try:
            self.socket.sendto(cmd_payload.encode(), (self.clearcore_ip, self.clearcore_port))
            logger.debug(f"Sent to ClearCore: {cmd_payload}")
            return True
        except Exception as e:
            logger.error(f"Failed to send to ClearCore: {e}")
            return False
    
    def _recv_clearcore_response(self, timeout=2.0):
        """Receive response from ClearCore (if query command)."""
        if self.phantom_mode:
            return str(self.last_position)
        
        if not self.socket:
            return "0"
        
        try:
            original_timeout = self.socket.gettimeout()
            self.socket.settimeout(timeout)
            data, _ = self.socket.recvfrom(1024)
            self.socket.settimeout(original_timeout)
            return data.decode('utf-8', errors='ignore').strip()
        except socket.timeout:
            return "0"
        except Exception as e:
            logger.error(f"Error receiving from ClearCore: {e}")
            return "0"
    
    def _handle_enable(self):
        """Enable axis E."""
        cmd = "BOARD:1;CMD:S1B1 ENABLE"
        self._send_clearcore_cmd(cmd)
        logger.info("Axis E enabled")
        return "1"
    
    def _handle_disable(self):
        """Disable axis E."""
        cmd = "BOARD:1;CMD:S1B1 DISABLE"
        self._send_clearcore_cmd(cmd)
        logger.info("Axis E disabled")
        return "0"
    
    def _handle_absolute_move(self, position):
        """Absolute position move for axis E."""
        self.last_position = position
        self.commanded_position = position
        pulses = int(position)
        cmd = f"BOARD:1;CMD:S1_Parameters:250,2000,{pulses}"
        self._send_clearcore_cmd(cmd)
        logger.info(f"Axis E absolute move to {position}")
        return "1"
    
    def _handle_relative_move(self, delta):
        """Relative position move for axis E."""
        new_position = self.last_position + delta
        self.last_position = new_position
        self.commanded_position = new_position
        pulses = int(new_position)
        cmd = f"BOARD:1;CMD:S1_Parameters:250,2000,{pulses}"
        self._send_clearcore_cmd(cmd)
        logger.info(f"Axis E relative move by {delta}")
        return "1"
    
    def _handle_set_speed(self, velocity):
        """Set speed for axis E."""
        pulses = int(self.last_position)
        cmd = f"BOARD:1;CMD:S1_Parameters:{int(velocity)},2000,{pulses}"
        self._send_clearcore_cmd(cmd)
        logger.info(f"Axis E speed set to {velocity}")
        return "1"
    
    def _handle_set_accel(self, accel):
        """Set acceleration for axis E."""
        pulses = int(self.last_position)
        cmd = f"BOARD:1;CMD:S1_Parameters:250,{int(accel)},{pulses}"
        self._send_clearcore_cmd(cmd)
        logger.info(f"Axis E accel set to {accel}")
        return "1"
    
    def _handle_set_decel(self, decel):
        """Set deceleration for axis E."""
        # ClearCore treats decel as accel in parameters
        self._handle_set_accel(decel)
        return "1"
    
    def _handle_clear_position(self):
        """Clear position (zero) for axis E."""
        cmd = "BOARD:1;CMD:S1_ClearPosition"
        self._send_clearcore_cmd(cmd)
        self.last_position = 0
        self.commanded_position = 0
        logger.info("Axis E position cleared")
        return "1"
    
    def _handle_query_position(self):
        """Query actual position for axis E."""
        cmd = "BOARD:1;CMD:REQUEST_VALUES"
        self._send_clearcore_cmd(cmd)
        response = self._recv_clearcore_response()
        # Parse response to extract position (could be in VALUES: format)
        try:
            if 'VALUES:' in response:
                parts = response.split('VALUES:')[1].split(',')
                if len(parts) >= 3:
                    return parts[2].strip()
            # Fall back to cached position
            return str(self.last_position)
        except Exception:
            return str(self.last_position)
    
    def _handle_query_status(self):
        """Query enable/disable status for axis E."""
        cmd = "BOARD:1;CMD:REQUEST_BUTTON_STATES"
        self._send_clearcore_cmd(cmd)
        # For now, return 1 (assume enabled)
        # TODO: Parse button states from response
        return "1"
    
    def _handle_query_speed(self):
        """Query current speed for axis E."""
        # ClearCore doesn't directly report current speed
        return "0"
    
    def _handle_stop(self):
        """Stop axis E motion."""
        cmd = "BOARD:1;CMD:S1B2 STOP"
        self._send_clearcore_cmd(cmd)
        logger.info("Axis E stopped")
        return "1"
    
    def shutdown(self):
        """Graceful shutdown of ClearCore connection."""
        logger.info("Shutting down ClearCore adapter...")
        
        if self.socket:
            try:
                self.socket.close()
                self.socket = None
                logger.info("ClearCore socket closed")
            except Exception as e:
                logger.error(f"Error closing ClearCore socket: {e}")
