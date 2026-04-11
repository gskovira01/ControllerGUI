"""
TIM Motion Service - Mock RapidCode Controller
===============================================

For development and testing without real RapidCode hardware.
Drop-in replacement for RSI.RapidCode.MotionController when phantom_mode=True.
"""

import logging

logger = logging.getLogger(__name__)


class MockMotionController:
    """Mock RapidCode motion controller for testing."""
    
    def __init__(self, num_axes=8):
        """Initialize mock controller."""
        self.num_axes = num_axes
        self.connected = False
        self.axes = {chr(65+i): MockAxis(i) for i in range(num_axes)}
        logger.info(f"Mock motion controller created with {num_axes} axes")
    
    def Connect(self):
        """Mock connection."""
        self.connected = True
        logger.info("Mock controller connected")
    
    def Disconnect(self):
        """Mock disconnection."""
        self.connected = False
        logger.info("Mock controller disconnected")
    
    def Axis(self, axis_num):
        """Get mock axis by number (0-based)."""
        axis_letter = chr(65 + axis_num)
        return self.axes.get(axis_letter, None)
    
    def AllMotionStop(self):
        """Stop all axes."""
        for axis in self.axes.values():
            axis.stop()
        logger.info("All axes stopped")
    
    def Shutdown(self):
        """Shutdown controller."""
        self.Disconnect()
        logger.info("Mock controller shutdown")


class MockAxis:
    """Mock RapidCode axis for testing."""
    
    def __init__(self, axis_num):
        """Initialize mock axis."""
        self.axis_num = axis_num
        self.axis_letter = chr(65 + axis_num)
        self.position = 0.0
        self.velocity = 0.0
        self.acceleration = 10.0
        self.deceleration = 10.0
        self.enabled = False
        self.moving = False
    
    def Enable(self):
        """Mock enable."""
        self.enabled = True
        logger.info(f"Axis {self.axis_letter} enabled (mock)")
    
    def Disable(self):
        """Mock disable."""
        self.enabled = False
        self.moving = False
        logger.info(f"Axis {self.axis_letter} disabled (mock)")
    
    def MoveAbsolute(self, position):
        """Mock absolute move."""
        if not self.enabled:
            logger.warning(f"Axis {self.axis_letter} not enabled")
            return
        self.position = position
        self.moving = True
        logger.info(f"Axis {self.axis_letter} moving to {position}")
    
    def MoveRelative(self, delta):
        """Mock relative move."""
        if not self.enabled:
            logger.warning(f"Axis {self.axis_letter} not enabled")
            return
        self.position += delta
        self.moving = True
        logger.info(f"Axis {self.axis_letter} moving by {delta}")
    
    def SetVelocity(self, velocity):
        """Mock set velocity."""
        self.velocity = velocity
        logger.debug(f"Axis {self.axis_letter} velocity set to {velocity}")
    
    def SetAcceleration(self, accel):
        """Mock set acceleration."""
        self.acceleration = accel
        logger.debug(f"Axis {self.axis_letter} acceleration set to {accel}")
    
    def SetDeceleration(self, decel):
        """Mock set deceleration."""
        self.deceleration = decel
        logger.debug(f"Axis {self.axis_letter} deceleration set to {decel}")
    
    def GetPosition(self):
        """Mock get position."""
        return self.position
    
    def GetVelocity(self):
        """Mock get velocity."""
        return self.velocity
    
    def IsEnabled(self):
        """Mock is enabled check."""
        return self.enabled
    
    def IsMoving(self):
        """Mock is moving check."""
        return self.moving
    
    def Stop(self):
        """Mock stop."""
        self.moving = False
        logger.info(f"Axis {self.axis_letter} stopped (mock)")
    
    def ClearPosition(self):
        """Mock clear position."""
        self.position = 0.0
        logger.info(f"Axis {self.axis_letter} position cleared (mock)")
