"""
================================================================================
                        RMP MOTION CONTROLLER WRAPPER
================================================================================

Author: gskovira01 (with Claude)
Last Updated: January 13, 2026
Version: 1.0.0

PURPOSE:
    Wrapper class for RapidCode Motion Platform (RMP) to replace Galil gclib
    Provides similar API to existing Galil integration for easy migration
    Adds PVT (Position-Velocity-Time) streaming capabilities for smooth contours

KEY FEATURES:
    - Compatible with existing ControllerGUI architecture
    - Testing mode with phantom axes (no hardware needed)
    - Point-to-point motion (maintains existing functionality)
    - PVT streaming for smooth multi-axis trajectories
    - Similar API to gclib for minimal code changes

USAGE:
    # Testing mode (no hardware)
    rmp = RMPController(use_hardware=False, num_axes=8)
    rmp.connect()
    rmp.enable_motors()
    rmp.move_absolute(0, 45.0)  # Move axis A to 45 degrees
    
    # PVT streaming
    trajectory = rmp.generate_pvt_from_waypoints(waypoints, total_time=2.0)
    rmp.stream_pvt_trajectory(trajectory)

CONFIGURATION:
    Set counts_per_degree for each axis based on your encoder + gear ratio
    Adjust motion parameters (velocity, acceleration) as needed
    Set software limits for safety

================================================================================
"""

from RSI.RapidCode import *
import numpy as np
from typing import List, Tuple, Dict, Optional
import time
import logging

logging.basicConfig(filename='rmp_controller.log',
                   level=logging.INFO,
                   format='%(asctime)s %(levelname)s: %(message)s')


class RMPController:
    """
    Wrapper class to replace Galil gclib with RMP RapidCode
    Maintains similar API for easy migration from CommMode1
    """
    
    def __init__(self, use_hardware=False, num_axes=8):
        """
        Initialize RMP controller
        
        Args:
            use_hardware: If False, uses phantom axes for testing
            num_axes: Number of axes in system (default 8 for your controller)
        """
        self.controller = None
        self.axes = []
        self.num_axes = num_axes
        self.use_hardware = use_hardware
        self.connected = False
        
        # Configuration - adjust for your motors
        # These should match your current Galil encoder counts per degree
        self.counts_per_degree = {
            0: 91.02,  # Axis A
            1: 91.02,  # Axis B
            2: 91.02,  # Axis C
            3: 91.02,  # Axis D
            4: 91.02,  # Axis E
            5: 91.02,  # Axis F
            6: 91.02,  # Axis G
            7: 91.02   # Axis H
        }
        
        # Default motion parameters (degrees/sec, degrees/sec²)
        self.default_velocity = 100.0
        self.default_acceleration = 500.0
        self.default_deceleration = 500.0
        self.default_jerk = 75.0  # Percent for S-curve
        
        logging.info(f"RMPController initialized: use_hardware={use_hardware}, num_axes={num_axes}")
    
    def connect(self):
        """Initialize connection to RMP controller"""
        try:
            if self.use_hardware:
                # For hardware (when deployed to Linux/Pi)
                # You'll update this later for Linux deployment
                self.controller = MotionController.CreateFromSoftware()
                logging.info("Connected to RMP (hardware mode - will need Linux config)")
            else:
                # For testing on Windows without hardware
                self.controller = MotionController.CreateFromSoftware()
                logging.info("Connected to RMP (testing mode - phantom axes)")
            
            serial = self.controller.SerialNumberGet()
            version = self.controller.FirmwareVersionGet()
            
            print(f"✓ Connected to RMP Controller")
            print(f"  Serial: {serial}")
            print(f"  Firmware: {version}")
            
            # Initialize axes
            for i in range(self.num_axes):
                axis = self.controller.AxisGet(i)
                
                if not self.use_hardware:
                    # Configure as phantom axis for testing
                    axis.MotorTypeSet(RSIMotorType.RSIMotorTypePHANTOM)
                
                # Set user units (degrees instead of encoder counts)
                axis.UserUnitsSet(self.counts_per_degree[i])
                
                # Default motion parameters
                axis.VelocitySet(self.default_velocity)
                axis.AccelerationSet(self.default_acceleration)
                axis.DecelerationSet(self.default_deceleration)
                axis.JerkPercentSet(self.default_jerk)
                
                # Set software limits for safety (-180 to +180 degrees)
                axis.SoftwareLimitActionSet(
                    RSIAxisSoftwareLimit.RSIAxisSoftwareLimitPositivePosition,
                    RSIAction.RSIActionE_STOP
                )
                axis.SoftwareLimitActionSet(
                    RSIAxisSoftwareLimit.RSIAxisSoftwareLimitNegativePosition,
                    RSIAction.RSIActionE_STOP
                )
                axis.SoftwareLimitPositiveSet(180.0)
                axis.SoftwareLimitNegativeSet(-180.0)
                
                self.axes.append(axis)
            
            print(f"✓ Configured {self.num_axes} axes")
            self.connected = True
            logging.info(f"Successfully configured {self.num_axes} axes")
            return True
            
        except RsiError as e:
            error_msg = f"Connection Error: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Unexpected error during connection: {e}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            return False
    
    def disconnect(self):
        """Clean disconnect"""
        if self.controller:
            try:
                # Disable all motors before disconnect
                for axis in self.axes:
                    try:
                        axis.AmpEnableSet(False)
                    except:
                        pass
                
                self.controller.Delete()
                self.connected = False
                print("✓ Disconnected from RMP")
                logging.info("Disconnected from RMP")
            except Exception as e:
                logging.error(f"Error during disconnect: {e}")
    
    # ========================================================================
    # MOTOR CONTROL - Basic enable/disable
    # ========================================================================
    
    def enable_motors(self, axes=None):
        """
        Enable motor amplifiers
        
        Args:
            axes: List of axis indices to enable (None = all axes)
        """
        if axes is None:
            axes = range(self.num_axes)
        
        for i in axes:
            try:
                axis = self.axes[i]
                axis.Abort()  # Clear any pending motion
                axis.ClearFaults()
                axis.AmpEnableSet(True)
                print(f"  Axis {chr(65+i)}: Enabled")
                logging.info(f"Axis {i} ({chr(65+i)}) enabled")
            except RsiError as e:
                error_msg = f"Failed to enable axis {chr(65+i)}: {e.text}"
                print(f"✗ {error_msg}")
                logging.error(error_msg)
    
    def disable_motors(self, axes=None):
        """
        Disable motor amplifiers
        
        Args:
            axes: List of axis indices to disable (None = all axes)
        """
        if axes is None:
            axes = range(self.num_axes)
        
        for i in axes:
            try:
                axis = self.axes[i]
                axis.AmpEnableSet(False)
                print(f"  Axis {chr(65+i)}: Disabled")
                logging.info(f"Axis {i} ({chr(65+i)}) disabled")
            except RsiError as e:
                error_msg = f"Failed to disable axis {chr(65+i)}: {e.text}"
                print(f"✗ {error_msg}")
                logging.error(error_msg)
    
    # ========================================================================
    # POINT-TO-POINT MOTION - Maintains existing functionality
    # ========================================================================
    
    def move_absolute(self, axis_num, position_degrees):
        """
        Move single axis to absolute position (replaces Galil PA command)
        
        Args:
            axis_num: Axis number (0-7 for A-H)
            position_degrees: Target position in degrees
        """
        try:
            axis = self.axes[axis_num]
            axis.MoveSCurve(position_degrees)  # S-curve for smooth motion
            logging.info(f"Axis {axis_num} ({chr(65+axis_num)}) move to {position_degrees}°")
        except RsiError as e:
            error_msg = f"Move failed for axis {chr(65+axis_num)}: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            raise
    
    def move_relative(self, axis_num, distance_degrees):
        """
        Move single axis relative distance (replaces Galil PR command)
        
        Args:
            axis_num: Axis number (0-7)
            distance_degrees: Relative distance in degrees
        """
        try:
            axis = self.axes[axis_num]
            current = axis.ActualPositionGet()
            target = current + distance_degrees
            axis.MoveSCurve(target)
            logging.info(f"Axis {axis_num} ({chr(65+axis_num)}) relative move {distance_degrees}°")
        except RsiError as e:
            error_msg = f"Relative move failed for axis {chr(65+axis_num)}: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            raise
    
    def move_all_axes(self, positions_degrees):
        """
        Move all axes to specified positions simultaneously
        Similar to Galil PA command
        
        Args:
            positions_degrees: List of positions [A, B, C, D, E, F, G, H] in degrees
        """
        try:
            # Command all axes
            for i, pos in enumerate(positions_degrees[:self.num_axes]):
                self.axes[i].MoveSCurve(pos)
            
            logging.info(f"Multi-axis move: {positions_degrees}")
        except RsiError as e:
            error_msg = f"Multi-axis move failed: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            raise
    
    # ========================================================================
    # STATUS & POSITION QUERIES
    # ========================================================================
    
    def get_positions(self):
        """Get current positions of all axes in degrees"""
        try:
            positions = [axis.ActualPositionGet() for axis in self.axes]
            return positions
        except RsiError as e:
            error_msg = f"Failed to get positions: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            return [0.0] * self.num_axes
    
    def get_position(self, axis_num):
        """Get current position of single axis in degrees"""
        try:
            return self.axes[axis_num].ActualPositionGet()
        except RsiError as e:
            error_msg = f"Failed to get position for axis {chr(65+axis_num)}: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            return 0.0
    
    def get_velocities(self):
        """Get current velocities of all axes in degrees/sec"""
        try:
            velocities = [axis.ActualVelocityGet() for axis in self.axes]
            return velocities
        except RsiError as e:
            error_msg = f"Failed to get velocities: {e.text}"
            logging.error(error_msg)
            return [0.0] * self.num_axes
    
    def is_moving(self, axis_num=None):
        """
        Check if axis is moving
        
        Args:
            axis_num: Axis to check (None = any axis)
        
        Returns:
            True if moving, False if stopped
        """
        try:
            if axis_num is not None:
                return not self.axes[axis_num].MotionDoneGet()
            else:
                # Check if any axis is moving
                return any(not axis.MotionDoneGet() for axis in self.axes)
        except RsiError as e:
            logging.error(f"Failed to check motion status: {e.text}")
            return False
    
    def wait_for_motion_done(self, axis_num=None, timeout_ms=-1):
        """
        Wait for motion to complete
        
        Args:
            axis_num: Axis to wait for (None = all axes)
            timeout_ms: Timeout in milliseconds (-1 = infinite)
        """
        try:
            if axis_num is not None:
                self.axes[axis_num].MotionDoneWait(timeout_ms)
            else:
                # Wait for all axes
                for axis in self.axes:
                    axis.MotionDoneWait(timeout_ms)
        except RsiError as e:
            error_msg = f"Motion wait error: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
    
    # ========================================================================
    # MOTION PARAMETERS - Velocity, Acceleration, etc.
    # ========================================================================
    
    def set_velocity(self, axis_num, velocity_deg_per_sec):
        """Set velocity for axis (degrees/sec)"""
        try:
            self.axes[axis_num].VelocitySet(velocity_deg_per_sec)
            logging.info(f"Axis {axis_num} velocity set to {velocity_deg_per_sec}°/s")
        except RsiError as e:
            logging.error(f"Failed to set velocity for axis {axis_num}: {e.text}")
    
    def set_acceleration(self, axis_num, accel_deg_per_sec2):
        """Set acceleration for axis (degrees/sec²)"""
        try:
            self.axes[axis_num].AccelerationSet(accel_deg_per_sec2)
            logging.info(f"Axis {axis_num} acceleration set to {accel_deg_per_sec2}°/s²")
        except RsiError as e:
            logging.error(f"Failed to set acceleration for axis {axis_num}: {e.text}")
    
    def set_deceleration(self, axis_num, decel_deg_per_sec2):
        """Set deceleration for axis (degrees/sec²)"""
        try:
            self.axes[axis_num].DecelerationSet(decel_deg_per_sec2)
            logging.info(f"Axis {axis_num} deceleration set to {decel_deg_per_sec2}°/s²")
        except RsiError as e:
            logging.error(f"Failed to set deceleration for axis {axis_num}: {e.text}")
    
    # ========================================================================
    # PVT STREAMING - NEW CAPABILITY for smooth trajectories
    # ========================================================================
    
    def stream_pvt_trajectory(self, trajectory_data, axes_to_use=None):
        """
        Stream PVT trajectory for smooth, blended motion
        This is your upgrade from point-to-point!
        
        Args:
            trajectory_data: Dict with structure:
            {
                'positions': [[p0_ax0, p0_ax1, ...], [p1_ax0, p1_ax1, ...], ...],  # degrees
                'velocities': [[v0_ax0, v0_ax1, ...], [v1_ax0, v1_ax1, ...], ...], # deg/s
                'times': [dt0, dt1, dt2, ...]  # seconds
            }
            axes_to_use: List of axis indices to include (None = all axes)
        """
        positions = np.array(trajectory_data['positions'])  # Shape: (num_points, num_axes)
        velocities = np.array(trajectory_data['velocities'])
        times = np.array(trajectory_data['times'])
        
        num_points = len(times)
        
        # Determine which axes to use
        if axes_to_use is None:
            axes_to_use = list(range(min(self.num_axes, positions.shape[1])))
        
        # Create MultiAxis for coordinated motion
        multi_axis = self.controller.MultiAxisGet(0)
        multi_axis.ClearAxes()  # Clear any previous configuration
        
        # Add selected axes to MultiAxis
        for axis_idx in axes_to_use:
            multi_axis.AxisAdd(self.axes[axis_idx])
        
        print(f"Streaming PVT trajectory: {num_points} points, {len(axes_to_use)} axes")
        logging.info(f"PVT stream: {num_points} points, axes {axes_to_use}")
        
        # Extract only the columns for axes we're using
        positions_subset = positions[:, axes_to_use]
        velocities_subset = velocities[:, axes_to_use]
        
        # Flatten arrays for RMP API (interleaved by axis)
        positions_flat = positions_subset.flatten(order='C')
        velocities_flat = velocities_subset.flatten(order='C')
        
        try:
            # Stream PVT motion
            multi_axis.MovePVT(
                positions_flat,
                velocities_flat,
                times,
                num_points,
                -1,    # emptyCount (-1 = no e-stop on buffer empty)
                False, # retain points
                True   # final = True (this is the complete trajectory)
            )
            
            print(f"✓ PVT trajectory loaded to controller")
            logging.info("PVT trajectory successfully loaded")
            
            # Motion executes immediately, wait for completion
            multi_axis.MotionDoneWait()
            print(f"✓ PVT trajectory complete")
            logging.info("PVT trajectory execution complete")
            
        except RsiError as e:
            error_msg = f"PVT Streaming Error: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
            raise
    
    def generate_pvt_from_waypoints(self, waypoints, total_time):
        """
        Helper: Generate PVT data from simple waypoints
        Calculates velocities automatically
        
        Args:
            waypoints: List of joint positions [[j0,j1,...], [j0,j1,...], ...]
            total_time: Total time for trajectory (seconds)
        
        Returns:
            trajectory_data dict ready for stream_pvt_trajectory()
        """
        waypoints = np.array(waypoints)
        num_points = len(waypoints)
        
        # Generate time deltas (equal spacing)
        times = np.full(num_points, total_time / num_points)
        
        # Calculate velocities between waypoints
        velocities = []
        for i in range(num_points):
            if i == 0:
                # First point: velocity based on next point
                vel = (waypoints[1] - waypoints[0]) / times[0]
            elif i == num_points - 1:
                # Last point: velocity based on previous point
                vel = (waypoints[i] - waypoints[i-1]) / times[i]
            else:
                # Middle points: average velocity
                vel = (waypoints[i+1] - waypoints[i-1]) / (times[i] + times[i+1])
            
            velocities.append(vel)
        
        return {
            'positions': waypoints.tolist(),
            'velocities': velocities,
            'times': times.tolist()
        }
    
    # ========================================================================
    # UTILITY FUNCTIONS
    # ========================================================================
    
    def zero_position(self, axis_num):
        """Set current position as zero for specified axis"""
        try:
            self.axes[axis_num].PositionSet(0.0)
            print(f"✓ Axis {chr(65+axis_num)} zeroed")
            logging.info(f"Axis {axis_num} ({chr(65+axis_num)}) position zeroed")
        except RsiError as e:
            error_msg = f"Failed to zero axis {chr(65+axis_num)}: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)
    
    def abort_motion(self, axis_num=None):
        """
        Abort motion on specified axis or all axes
        
        Args:
            axis_num: Axis to abort (None = all axes)
        """
        try:
            if axis_num is not None:
                self.axes[axis_num].Abort()
                print(f"✓ Axis {chr(65+axis_num)} motion aborted")
                logging.info(f"Axis {axis_num} motion aborted")
            else:
                for i, axis in enumerate(self.axes):
                    axis.Abort()
                print("✓ All motion aborted")
                logging.info("All axes motion aborted")
        except RsiError as e:
            error_msg = f"Failed to abort motion: {e.text}"
            print(f"✗ {error_msg}")
            logging.error(error_msg)


# ========================================================================
# EXAMPLE USAGE & TESTING
# ========================================================================

if __name__ == "__main__":
    print("="*60)
    print("RMP Controller Test - Phantom Axes Mode")
    print("="*60)
    
    # Initialize controller in testing mode
    rmp = RMPController(use_hardware=False, num_axes=8)
    
    if rmp.connect():
        rmp.enable_motors()
        
        # Test 1: Simple point-to-point (your current method)
        print("\n--- Test 1: Point-to-Point Motion ---")
        rmp.move_absolute(0, 45.0)  # Move axis A to 45 degrees
        rmp.wait_for_motion_done(0)
        print(f"Axis A position: {rmp.get_position(0):.2f}°")
        
        # Test 2: Multi-axis move
        print("\n--- Test 2: Multi-Axis Move ---")
        positions = [10, 20, 30, 40, 50, 60, 70, 80]
        rmp.move_all_axes(positions)
        rmp.wait_for_motion_done()
        current = rmp.get_positions()
        print(f"All positions: {[f'{p:.1f}' for p in current]}")
        
        # Test 3: PVT streaming (your upgrade!)
        print("\n--- Test 3: PVT Streaming ---")
        
        # Define simple waypoints (8 axes × 4 waypoints)
        waypoints = [
            [0, 0, 0, 0, 0, 0, 0, 0],       # Starting
            [45, 10, -30, 20, 0, 15, -10, 5],   # Point 1
            [90, 20, -60, 40, 10, 30, -20, 10], # Point 2
            [-45, -10, 30, -20, -5, -15, 10, -5] # Point 3
        ]
        
        # Generate PVT trajectory
        pvt_data = rmp.generate_pvt_from_waypoints(waypoints, total_time=2.0)
        
        # Stream to controller
        rmp.stream_pvt_trajectory(pvt_data)
        
        final = rmp.get_positions()
        print(f"Final positions: {[f'{p:.1f}' for p in final]}")
        
        rmp.disable_motors()
        rmp.disconnect()
        
        print("\n" + "="*60)
        print("✓ All tests completed successfully!")
        print("="*60)
