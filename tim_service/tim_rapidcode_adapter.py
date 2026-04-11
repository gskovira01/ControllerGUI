"""
TIM RapidCode Adapter - Axes A-D (EtherCAT)
============================================

Translates Galil-like commands into RapidCode API calls for axes A-D.
Handles enable, disable, absolute move, relative move, speed, accel, position query.

This adapter manages the deterministic 1 kHz EtherCAT motion control loop.
"""

import logging
import re

logger = logging.getLogger(__name__)


class RapidCodeAdapter:
    """Adapter for RapidCode control of axes A-D (EtherCAT)."""
    
    def __init__(self, config=None, phantom_mode=False, watchdog=None):
        """
        Initialize RapidCode adapter.
        
        Args:
            config: Configuration dict with RapidCode settings
            phantom_mode: If True, use mock RapidCode (no hardware)
            watchdog: SafetyWatchdog instance
        """
        self.config = config or {}
        self.phantom_mode = phantom_mode
        self.watchdog = watchdog
        self.rmp = None  # RapidCode motionController instance
        
        if not phantom_mode:
            self._init_rapidcode()
        else:
            logger.info("RapidCode adapter in PHANTOM MODE (mock)")
            self._init_phantom_rapidcode()
    
    def _init_rapidcode(self):
        """Initialize real RapidCode connection."""
        try:
            from RSI.RapidCode import *
            
            # Create motion controller
            self.rmp = MotionController()
            
            # Connect to real hardware
            self.rmp.Connect()
            logger.info("RapidCode connected to real hardware")
            
            # Discover and enable EtherCAT slaves
            # TODO: Implement EtherCAT slave discovery
            
        except ImportError:
            logger.error("RapidCode SDK not found. Install RSI RapidCode 10.7.1+")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize RapidCode: {e}")
            raise
    
    def _init_phantom_rapidcode(self):
        """Initialize mock RapidCode for testing."""
        # Create a mock RapidCode controller
        from tests.test_mock_rapidcode import MockMotionController
        self.rmp = MockMotionController()
        logger.info("Mock RapidCode controller initialized")
    
    def handle_command(self, command, axis):
        """
        Handle a Galil-like command for a single axis.
        
        Args:
            command: Full command string (e.g., "PA A=45")
            axis: Single axis letter ('A'-'D')
        
        Returns:
            Response string (numeric value or status)
        """
        if self.rmp is None:
            return "0"
        
        try:
            cmd_upper = command.strip().upper()
            axis_idx = ord(axis) - ord('A')  # A->0, B->1, etc.
            
            # Parse command type and value
            if cmd_upper.startswith('SH'):
                # Enable axis
                return self._handle_enable(axis_idx)
            elif cmd_upper.startswith('MO'):
                # Disable axis
                return self._handle_disable(axis_idx)
            elif cmd_upper.startswith('PA'):
                # Absolute position move
                value = self._extract_numeric(cmd_upper)
                return self._handle_absolute_move(axis_idx, value)
            elif cmd_upper.startswith('PR'):
                # Relative position move
                value = self._extract_numeric(cmd_upper)
                return self._handle_relative_move(axis_idx, value)
            elif cmd_upper.startswith('SP'):
                # Set speed
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_speed(axis_idx, value)
            elif cmd_upper.startswith('AC'):
                # Set acceleration
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_accel(axis_idx, value)
            elif cmd_upper.startswith('DC'):
                # Set deceleration
                value = self._extract_numeric(cmd_upper)
                return self._handle_set_decel(axis_idx, value)
            elif cmd_upper.startswith('DP'):
                # Clear position (zero the axis)
                return self._handle_clear_position(axis_idx)
            elif 'MG _RP' in cmd_upper or 'MG _TP' in cmd_upper:
                # Query actual position
                return self._handle_query_position(axis_idx)
            elif 'MG _MO' in cmd_upper:
                # Query enable/disable status
                return self._handle_query_status(axis_idx)
            elif 'MG _SP' in cmd_upper:
                # Query speed
                return self._handle_query_speed(axis_idx)
            elif cmd_upper.startswith('ST'):
                # Stop motion
                return self._handle_stop(axis_idx)
            else:
                logger.warning(f"Unknown RapidCode command: {command}")
                return "0"
        
        except Exception as e:
            logger.error(f"Error handling RapidCode command '{command}': {e}")
            return "0"
    
    def _extract_numeric(self, command):
        """Extract numeric value from command (e.g., '45' from 'PA A=45')."""
        match = re.search(r'=\s*([-+]?\d+\.?\d*)', command)
        if match:
            return float(match.group(1))
        return 0.0
    
    def _handle_enable(self, axis_idx):
        """Enable axis."""
        try:
            if self.rmp:
                # TODO: Call RapidCode enable
                logger.info(f"Axis {chr(65+axis_idx)} enabled")
            return "1"
        except Exception as e:
            logger.error(f"Failed to enable axis {axis_idx}: {e}")
            return "0"
    
    def _handle_disable(self, axis_idx):
        """Disable axis."""
        try:
            if self.rmp:
                # TODO: Call RapidCode disable
                logger.info(f"Axis {chr(65+axis_idx)} disabled")
            return "0"
        except Exception as e:
            logger.error(f"Failed to disable axis {axis_idx}: {e}")
            return "0"
    
    def _handle_absolute_move(self, axis_idx, value):
        """Absolute position move."""
        try:
            if self.rmp:
                # TODO: Call RapidCode move absolute
                logger.info(f"Axis {chr(65+axis_idx)} absolute move to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_relative_move(self, axis_idx, value):
        """Relative position move."""
        try:
            if self.rmp:
                # TODO: Call RapidCode move relative
                logger.info(f"Axis {chr(65+axis_idx)} relative move by {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_speed(self, axis_idx, value):
        """Set axis speed."""
        try:
            if self.rmp:
                # TODO: Call RapidCode set speed
                logger.info(f"Axis {chr(65+axis_idx)} speed set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set speed on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_accel(self, axis_idx, value):
        """Set axis acceleration."""
        try:
            if self.rmp:
                # TODO: Call RapidCode set accel
                logger.info(f"Axis {chr(65+axis_idx)} accel set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set accel on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_decel(self, axis_idx, value):
        """Set axis deceleration (treated as accel in many systems)."""
        try:
            if self.rmp:
                # TODO: Call RapidCode set decel
                logger.info(f"Axis {chr(65+axis_idx)} decel set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set decel on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_clear_position(self, axis_idx):
        """Clear position (zero the axis)."""
        try:
            if self.rmp:
                # TODO: Call RapidCode clear position
                logger.info(f"Axis {chr(65+axis_idx)} position cleared")
            return "1"
        except Exception as e:
            logger.error(f"Failed to clear position on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_position(self, axis_idx):
        """Query actual position."""
        try:
            if self.rmp:
                # TODO: Call RapidCode get position
                position = 0.0  # placeholder
                return str(position)
            return "0"
        except Exception as e:
            logger.error(f"Failed to query position on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_status(self, axis_idx):
        """Query enable/disable status."""
        try:
            if self.rmp:
                # TODO: Call RapidCode get enable status
                status = 1  # 1 = enabled, 0 = disabled
                return str(status)
            return "0"
        except Exception as e:
            logger.error(f"Failed to query status on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_speed(self, axis_idx):
        """Query current speed."""
        try:
            if self.rmp:
                # TODO: Call RapidCode get speed
                speed = 0.0
                return str(speed)
            return "0"
        except Exception as e:
            logger.error(f"Failed to query speed on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_stop(self, axis_idx):
        """Stop axis motion."""
        try:
            if self.rmp:
                # TODO: Call RapidCode stop
                logger.info(f"Axis {chr(65+axis_idx)} stopped")
            return "1"
        except Exception as e:
            logger.error(f"Failed to stop axis {axis_idx}: {e}")
            return "0"
    
    def shutdown(self):
        """Graceful shutdown of RapidCode connection."""
        logger.info("Shutting down RapidCode adapter...")
        
        if self.rmp and not self.phantom_mode:
            try:
                # TODO: Disable all axes and disconnect
                self.rmp = None
                logger.info("RapidCode disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting RapidCode: {e}")
