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
import re
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
        self._unsupported_axis_logged = set()
        
        # Initialize hardware adapters
        self.rapidcode = RapidCodeAdapter(
            config=self.config.get('rapidcode', {}),
            phantom_mode=phantom_mode,
            watchdog=watchdog
        )
        
        self.clearcore = ClearCoreAdapter(
            config=self.config.get('clearcore', {}),
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
        
        # Handle broadcast commands (no axis)
        # [CHANGE 2026-04-17 16:45:00 -04:00] Support MG _GN and other broadcast queries.
        if command == 'MG _GN':
            # Generation/ping query — return "1" to indicate alive
            return "1"
        
        # Extract axis letter (e.g., 'A' from "PA A=45" or "SH A")
        axis = self._extract_axis(command)
        
        if axis is None:
            # Bare "ST" with no axis letter = broadcast stop all axes.
            if command == 'ST':
                results = []
                for ax in ('A', 'B', 'C', 'D'):
                    try:
                        results.append(self.rapidcode.handle_command(f'ST{ax}', ax))
                    except Exception as e:
                        logger.error("Broadcast ST failed for axis %s: %s", ax, e)
                try:
                    results.append(self.clearcore.handle_command('STE', 'E'))
                except Exception as e:
                    logger.error("Broadcast ST failed for axis E: %s", e)
                logger.info("Broadcast ST sent to all axes: %s", results)
                return "1"
            logger.warning(f"Could not determine axis from command: {command}")
            return "0"
        
        # Route to appropriate adapter
        if axis in ('A', 'B', 'C', 'D'):
            return self.rapidcode.handle_command(command, axis)
        elif axis == 'E':
            return self.clearcore.handle_command(command, axis)
        else:
            if axis not in self._unsupported_axis_logged:
                logger.warning(f"Axis {axis} not supported")
                self._unsupported_axis_logged.add(axis)
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
        # [CHANGE 2026-04-11 12:09:00 -04:00] Parse explicit MG/TP query suffix axis first.
        mg_match = re.search(r'\b(?:MG\s+_\w+|TP\s+_?\w*)([A-H])\b', command)
        if mg_match:
            return mg_match.group(1)

        # Commands with explicit axis token: "SH A", "PA A=45", "DP A"
        token_match = re.match(r'^\s*[A-Z_]+\s+([A-H])(?:\b|\s*=|=)', command)
        if token_match:
            return token_match.group(1)

        # Compact commands with axis suffix: "SHE", "MOE", "DPA", "PRA=10", "BGA"
        # [CHANGE 2026-04-17 16:50:00 -04:00] Added BG (start motion) to compact pattern.
        compact_match = re.match(r'^\s*(?:SH|MO|ST|DP|TP|PA|PR|SP|AC|DC|BG)([A-H])(?:\b|=)', command)
        if compact_match:
            return compact_match.group(1)

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
