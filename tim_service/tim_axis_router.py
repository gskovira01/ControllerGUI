"""
TIM Axis Router - Command Dispatcher
=====================================

Routes Galil-like ASCII commands to the correct subsystem:
- Axes A-D: RapidCode (EtherCAT motor control)
- Axis E: ClearCore (auxiliary steering axis)
- Axes F-H: Unused/disabled

Translates commands like "PA A=45" into RapidCode calls for motion execution.
"""

import logging
from tim_rapidcode_adapter import RapidCodeAdapter
from tim_clearcore_adapter import ClearCoreAdapter

logger = logging.getLogger(__name__)


class AxisRouter:
    """Routes motion commands to appropriate hardware adapter."""
    
    def __init__(self, config=None, phantom_mode=False, watchdog=None):
        """
        Initialize axis router.
        
        Args:
            config: Configuration dict from yaml
            phantom_mode: If True, use mock adapters
            watchdog: SafetyWatchdog instance
        """
        self.config = config or {}
        self.phantom_mode = phantom_mode
        self.watchdog = watchdog
        
        # Initialize hardware adapters
        self.rapidcode = RapidCodeAdapter(
            config=config.get('rapidcode', {}),
            phantom_mode=phantom_mode,
            watchdog=watchdog
        )
        
        self.clearcore = ClearCoreAdapter(
            config=config.get('clearcore', {}),
            phantom_mode=phantom_mode,
            watchdog=watchdog
        )
        
        logger.info("Axis router initialized")
    
    def dispatch(self, command):
        """
        Dispatch a Galil-like command to the appropriate axis.
        
        Args:
            command: Galil-style ASCII command (e.g., "PA A=45")
        
        Returns:
            Response string (numeric value or status)
        """
        command = command.strip().upper()
        
        if not command:
            return "0"
        
        # Extract axis letter (e.g., 'A' from "PA A=45" or "SH A")
        axis = self._extract_axis(command)
        
        if axis is None:
            logger.warning(f"Could not determine axis from command: {command}")
            return "0"
        
        # Route to appropriate adapter
        if axis in ('A', 'B', 'C', 'D'):
            return self.rapidcode.handle_command(command, axis)
        elif axis == 'E':
            return self.clearcore.handle_command(command, axis)
        else:
            logger.warning(f"Axis {axis} not supported")
            return "0"
    
    def _extract_axis(self, command):
        """
        Extract axis letter from command.
        
        Examples:
            "SH A" -> 'A'
            "PA A=45" -> 'A'
            "MG _RPA" -> 'A'
            "TP" -> None (broadcast)
        
        Returns:
            Axis letter ('A'-'H') or None
        """
        # Common patterns: "CMD A", "CMD A=value", "CMD_XPA"
        for i, char in enumerate(command):
            if char in 'ABCDEFGH':
                # Verify it looks like an axis reference
                # (preceded by space, '=', or underscore)
                if i == 0 or command[i-1] in (' ', '=', '_'):
                    return char
        
        return None
    
    def shutdown(self):
        """Graceful shutdown of all adapters."""
        logger.info("Shutting down axis router...")
        
        try:
            self.rapidcode.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down RapidCode adapter: {e}")
        
        try:
            self.clearcore.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down ClearCore adapter: {e}")
        
        logger.info("Axis router shutdown complete")
