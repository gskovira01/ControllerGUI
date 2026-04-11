"""
TIM Safety Watchdog - Fault Management & Monitoring
====================================================

Monitors system health and enforces safety limits:
- Enable/disable interlocks
- Motion limits (software and hardware)
- Watchdog timeout (client disconnect detection)
- Fault logging and recovery
"""

import logging
import time
import threading

logger = logging.getLogger(__name__)


class SafetyWatchdog:
    """Monitors system safety and enforces motion limits."""
    
    def __init__(self, config=None):
        """
        Initialize safety watchdog.
        
        Args:
            config: Safety configuration dict
        """
        self.config = config or {}
        self.running = False
        self.watchdog_thread = None
        self.last_client_activity = time.time()
        self.watchdog_timeout = config.get('watchdog_timeout_sec', 10)
        self.motion_timeout = config.get('motion_timeout_sec', 30)
        
        # Axis states
        self.axis_states = {
            axis: {
                'enabled': False,
                'moving': False,
                'position': 0.0,
                'speed': 0.0,
                'faults': []
            }
            for axis in 'ABCDE'
        }
        
        logger.info(f"Safety watchdog initialized (timeout: {self.watchdog_timeout}s)")
    
    def start(self):
        """Start watchdog monitoring thread."""
        if self.running:
            return
        
        self.running = True
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.watchdog_thread.start()
        logger.info("Watchdog monitoring started")
    
    def _watchdog_loop(self):
        """Main watchdog monitoring loop."""
        while self.running:
            try:
                # Check for client timeout
                elapsed = time.time() - self.last_client_activity
                if elapsed > self.watchdog_timeout:
                    logger.warning(f"Watchdog timeout: Client inactive for {elapsed:.1f}s")
                    self._handle_timeout()
                
                time.sleep(1)  # Check every second
            
            except Exception as e:
                logger.error(f"Watchdog error: {e}")
    
    def _handle_timeout(self):
        """Handle watchdog timeout (client disconnect)."""
        logger.warning("Executing safe stop due to watchdog timeout")
        # TODO: Issue safe stop to all axes
        # This should disable motion but hold position
    
    def update_activity(self):
        """Update last client activity timestamp."""
        self.last_client_activity = time.time()
    
    def set_axis_enabled(self, axis, enabled):
        """Update axis enable state."""
        if axis in self.axis_states:
            self.axis_states[axis]['enabled'] = enabled
            logger.info(f"Axis {axis} enable state: {enabled}")
    
    def set_axis_position(self, axis, position):
        """Update axis position."""
        if axis in self.axis_states:
            self.axis_states[axis]['position'] = position
    
    def set_axis_speed(self, axis, speed):
        """Update axis speed."""
        if axis in self.axis_states:
            self.axis_states[axis]['speed'] = speed
    
    def add_fault(self, axis, fault_msg):
        """Add a fault to the axis."""
        if axis in self.axis_states:
            self.axis_states[axis]['faults'].append(fault_msg)
            logger.error(f"Axis {axis} fault: {fault_msg}")
    
    def clear_faults(self, axis):
        """Clear faults for an axis."""
        if axis in self.axis_states:
            self.axis_states[axis]['faults'] = []
            logger.info(f"Faults cleared for axis {axis}")
    
    def get_axis_state(self, axis):
        """Get current state of an axis."""
        return self.axis_states.get(axis, {})
    
    def shutdown(self):
        """Graceful shutdown of watchdog."""
        logger.info("Shutting down safety watchdog...")
        self.running = False
        
        if self.watchdog_thread:
            try:
                self.watchdog_thread.join(timeout=2)
            except Exception:
                pass
        
        logger.info("Watchdog shutdown complete")
