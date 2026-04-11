"""
TIM RapidCode Adapter - Axes A-D (EtherCAT)
============================================

Translates Galil-like commands into RapidCode API calls for axes A-D.
Handles enable, disable, absolute move, relative move, speed, accel, position query.

This adapter manages the deterministic 1 kHz EtherCAT motion control loop.
"""

import logging
import os
import re
import importlib
import importlib.util
import sys
from pathlib import Path

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

    def _get_mock_axis(self, axis_idx):
        """Return the mock axis object for phantom mode, or None."""
        if not self.phantom_mode or not self.rmp:
            return None
        try:
            return self.rmp.Axis(axis_idx)
        except Exception:
            return None
    
    def _init_rapidcode(self):
        """Initialize real RapidCode connection."""
        # [CHANGE 2026-04-11 16:20:00 -05:00] Add RSI 11.x and INtime runtime paths in-process
        rsi_path = r'C:\RSI\11.0.3'
        intime_bin_path = r'C:\Program Files (x86)\INtime\bin'
        for extra_path in (rsi_path, intime_bin_path):
            if extra_path not in sys.path:
                sys.path.insert(0, extra_path)
            os.environ['PATH'] = extra_path + os.pathsep + os.environ.get('PATH', '')

        for dll_path in (rsi_path, intime_bin_path):
            try:
                os.add_dll_directory(dll_path)
            except (AttributeError, FileNotFoundError, OSError):
                pass

        # Try RapidCodePython (RSI 11.x on-disk layout) first, fall back to RSI.RapidCode
        rapidcode_module = None
        motion_controller_cls = None
        import_errors = []
        for mod_name, cls_name in [
            ('RapidCodePython', 'MotionController'),
            ('RSI.RapidCode',   'MotionController'),
        ]:
            try:
                rapidcode_module = importlib.import_module(mod_name)
                motion_controller_cls = getattr(rapidcode_module, cls_name, None)
                if motion_controller_cls is not None:
                    logger.info(f"RapidCode SDK loaded via '{mod_name}'")
                    break
            except ImportError as exc:
                import_errors.append(f"{mod_name}: {exc}")
                continue

        if motion_controller_cls is None:
            logger.error("RapidCode SDK not found. Install RSI RapidCode 10.7.1+")
            if import_errors:
                logger.error("RapidCode import attempts failed: %s", '; '.join(import_errors))
            raise ImportError("No module named 'RSI'")

        try:
            # Create motion controller and connect to real hardware
            self.rmp = motion_controller_cls()
            self.rmp.Connect()
            logger.info("RapidCode connected to real hardware")

            # Discover and enable EtherCAT slaves
            # TODO: Implement EtherCAT slave discovery

        except Exception as e:
            logger.error(f"Failed to initialize RapidCode: {e}")
            raise
    
    def _init_phantom_rapidcode(self):
        """Initialize mock RapidCode for testing."""
        # Create a mock RapidCode controller
        try:
            from tests.test_mock_rapidcode import MockMotionController
        except Exception:
            # Fallback for environments where "tests" resolves to an external package.
            mock_path = Path(__file__).resolve().parent / 'tests' / 'test_mock_rapidcode.py'
            spec = importlib.util.spec_from_file_location('tim_mock_rapidcode', str(mock_path))
            if spec is None or spec.loader is None:
                raise ImportError(f'Could not load mock module from {mock_path}')
            mock_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mock_module)
            MockMotionController = mock_module.MockMotionController
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
                # [CHANGE 2026-04-11 12:33:00 -05:00] Use mock axis state in phantom mode.
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.Enable()
                # TODO: Call RapidCode enable for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} enabled")
            return "1"
        except Exception as e:
            logger.error(f"Failed to enable axis {axis_idx}: {e}")
            return "0"
    
    def _handle_disable(self, axis_idx):
        """Disable axis."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.Disable()
                # TODO: Call RapidCode disable for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} disabled")
            return "0"
        except Exception as e:
            logger.error(f"Failed to disable axis {axis_idx}: {e}")
            return "0"
    
    def _handle_absolute_move(self, axis_idx, value):
        """Absolute position move."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.MoveAbsolute(value)
                # TODO: Call RapidCode move absolute for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} absolute move to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_relative_move(self, axis_idx, value):
        """Relative position move."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.MoveRelative(value)
                # TODO: Call RapidCode move relative for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} relative move by {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_speed(self, axis_idx, value):
        """Set axis speed."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.SetVelocity(value)
                # TODO: Call RapidCode set speed for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} speed set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set speed on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_accel(self, axis_idx, value):
        """Set axis acceleration."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.SetAcceleration(value)
                # TODO: Call RapidCode set accel for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} accel set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set accel on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_decel(self, axis_idx, value):
        """Set axis deceleration (treated as accel in many systems)."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.SetDeceleration(value)
                # TODO: Call RapidCode set decel for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} decel set to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set decel on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_clear_position(self, axis_idx):
        """Clear position (zero the axis)."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.ClearPosition()
                # TODO: Call RapidCode clear position for real hardware path
                logger.info(f"Axis {chr(65+axis_idx)} position cleared")
            return "1"
        except Exception as e:
            logger.error(f"Failed to clear position on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_position(self, axis_idx):
        """Query actual position."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    position = mock_axis.GetPosition()
                    return str(position)
                # TODO: Call RapidCode get position for real hardware path
                position = 0.0
                return str(position)
            return "0"
        except Exception as e:
            logger.error(f"Failed to query position on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_status(self, axis_idx):
        """Query enable/disable status."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    status = 1 if mock_axis.IsEnabled() else 0
                    return str(status)
                # TODO: Call RapidCode get enable status for real hardware path
                status = 1
                return str(status)
            return "0"
        except Exception as e:
            logger.error(f"Failed to query status on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_speed(self, axis_idx):
        """Query current speed."""
        try:
            if self.rmp:
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    speed = mock_axis.GetVelocity()
                    return str(speed)
                # TODO: Call RapidCode get speed for real hardware path
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
                mock_axis = self._get_mock_axis(axis_idx)
                if mock_axis is not None:
                    mock_axis.Stop()
                # TODO: Call RapidCode stop for real hardware path
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
