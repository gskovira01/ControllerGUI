"""
================================================================================
MyActuator X10-100 Interactive Control Script
================================================================================
Interactive motor control via Waveshare CAN-to-ETH converter
Commands: move, speed, enable, disable, zero, status, quit
================================================================================
"""

import socket
import struct
import time

# ============================================================================
# CONFIGURATION
# ============================================================================
WAVESHARE_IP = '192.168.0.7'
WAVESHARE_PORT = 20001
MOTOR_ID = 1
MOTOR_CAN_ID = 0x140 + MOTOR_ID
MOTOR_REPLY_ID = 0x240 + MOTOR_ID

# Global zero offset
zero_offset = 0.0

def wrap_angle(angle):
    """Wrap angle to ±180° range"""
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle

# Commands
CMD_MOTOR_OFF = 0x80
CMD_MOTOR_ON = 0x88
CMD_ZERO_POSITION = 0x19
CMD_POSITION_CONTROL = 0xA4
CMD_SPEED_CONTROL = 0xA2
CMD_REQUEST_STATE = 0x9C

# ============================================================================
# CAN Communication
# ============================================================================

def create_can_frame(can_id, data):
    """Create Waveshare CAN frame: DLC + CAN_ID (big endian) + Data"""
    dlc = len(data)
    return struct.pack('B', dlc) + struct.pack('>I', can_id) + data + b'\x00' * (8 - dlc)

def send_can(sock, can_id, data):
    """Send CAN message"""
    frame = create_can_frame(can_id, data)
    sock.send(frame)

def receive_can(sock, timeout=1.0):
    """Receive CAN message"""
    sock.settimeout(timeout)
    try:
        data = sock.recv(1024)
        if len(data) >= 13:
            dlc = data[0] & 0x0F
            can_id = struct.unpack('>I', data[1:5])[0]
            payload = data[5:5+dlc]
            return can_id, payload
    except socket.timeout:
        pass
    return None, None

# ============================================================================
# Motor Commands
# ============================================================================

def motor_enable(sock):
    """Enable motor (release brake)"""
    data = bytes([CMD_MOTOR_ON, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None

def motor_disable(sock):
    """Disable motor (engage brake)"""
    data = bytes([CMD_MOTOR_OFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None

def set_zero(sock):
    """Set current position as zero"""
    data = bytes([CMD_ZERO_POSITION, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None

def get_motor_state(sock, apply_zero=True):
    """Get motor position, velocity, torque"""
    global zero_offset
    data = bytes([CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    
    if response and len(response) >= 8:
        # Parse response: temperature(1) + torque(2) + speed(2) + position(2)
        temp = struct.unpack('b', response[1:2])[0]  # signed byte
        torque = struct.unpack('<h', response[2:4])[0] * 0.01  # 0.01 Nm
        speed = struct.unpack('<h', response[4:6])[0] * 0.01   # 0.01 dps
        position_raw = struct.unpack('<h', response[6:8])[0]  # raw counts
        position_abs = position_raw * 0.01 # 0.01 deg (absolute)
        position = position_abs - zero_offset if apply_zero else position_abs
        return {'temp': temp, 'torque': torque, 'speed': speed, 'position': position, 
                'position_abs': position_abs, 'position_raw': position_raw}
    return None

def move_to_position(sock, position_deg, max_speed=100.0):
    """Move to position (degrees) at max speed (deg/s)"""
    global zero_offset
    
    # Speed is uint16_t, 1 dps/LSB, max = 65535 dps
    MAX_SPEED_DPS = 65535
    if max_speed > MAX_SPEED_DPS:
        print(f"  WARNING: Speed {max_speed} dps exceeds max {MAX_SPEED_DPS} dps, clamping")
        max_speed = MAX_SPEED_DPS
    
    # Add zero offset to get absolute position
    absolute_position = position_deg + zero_offset
    # Wrap to ±180° range for single-turn encoder
    wrapped_position = wrap_angle(absolute_position)
    position_counts = int(wrapped_position * 100)  # 0.01° units
    speed_counts = int(max_speed)  # 1 dps units (NOT 0.01!)
    
    # Pack data following 0xA8 pattern: CMD + NULL + speed(2) + position(4)
    # Format: A4 00 [speed_low] [speed_high] [pos_low] [pos_mid1] [pos_mid2] [pos_high]
    data = struct.pack('<BHi', 0x00, speed_counts, position_counts)
    data = bytes([CMD_POSITION_CONTROL]) + data
    
    print(f"  DEBUG: Sending position={wrapped_position:.2f}° ({position_counts} counts), speed={max_speed:.0f} dps")
    print(f"  DEBUG: Speed={speed_counts} dps, Full frame: {data.hex()}")
    
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None
    
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None

def move_with_monitoring(sock, position_deg, max_speed=100.0):
    """Move to position and display real-time feedback"""
    # Send move command
    if not move_to_position(sock, position_deg, max_speed):
        return False
    
    print(f"Moving to {position_deg}° at {max_speed} deg/s")
    print("Position   Raw      Speed      Torque    Temp")
    print("-" * 55)
    
    try:
        last_pos = None
        stationary_count = 0
        
        while True:
            state = get_motor_state(sock)
            if state:
                print(f"\r{state['position']:7.2f}°  {state['position_abs']:6.2f}°  {state['speed']:7.2f} dps  "
                      f"{state['torque']:6.2f} Nm  {state['temp']:3d}°C", end='', flush=True)
                
                # Check if motor has reached target and stopped
                position_error = abs(state['position'] - position_deg)
                
                if last_pos is not None:
                    # Stopped when: near target AND low speed AND position stable
                    if position_error < 5.0 and abs(state['speed']) < 2.0 and abs(state['position'] - last_pos) < 0.5:
                        stationary_count += 1
                        if stationary_count >= 5:  # 5 seconds stable
                            print()  # New line
                            break
                    else:
                        stationary_count = 0
                
                last_pos = state['position']
                time.sleep(1.0)
            else:
                time.sleep(1.0)
                
    except KeyboardInterrupt:
        print("\n(Monitoring stopped)")
    
    final_error = abs(last_pos - position_deg) if last_pos else 0
    print(f"✓ Reached position: {last_pos:.2f}° (error: {final_error:.2f}°)")
    return True

def set_speed(sock, speed_dps):
    """Set motor speed (deg/s) - continuous rotation"""
    speed_counts = int(speed_dps * 100)
    
    data = struct.pack('<iBBBB', speed_counts, 0x00, 0x00, 0x00, 0x00)
    data = bytes([CMD_SPEED_CONTROL]) + data[:7]
    
    send_can(sock, MOTOR_CAN_ID, data)
    can_id, response = receive_can(sock)
    return response is not None

# ============================================================================
# Interactive Control
# ============================================================================

def print_help():
    """Print available commands"""
    print("\n" + "="*70)
    print("COMMANDS:")
    print("="*70)
    print("  enable              - Enable motor (release brake)")
    print("  disable             - Disable motor (engage brake)")
    print("  zero                - Set current position as zero")
    print("  status              - Read motor state (position, speed, torque)")
    print("  move <deg> [speed]  - Move to absolute position (deg) at speed (deg/s)")
    print("  movemon <deg> [spd] - Move with real-time monitoring")
    print("  rel <deg> [speed]   - Move relative to current position (deg)")
    print("  speed <dps>         - Set continuous speed (deg/s)")
    print("  stop                - Stop motor immediately")
    print("  watch               - Continuously display motor status (Ctrl+C to stop)")
    print("  help                - Show this help")
    print("  quit                - Exit program")
    print("="*70)
    print("\nExamples:")
    print("  move 90             - Move to absolute position 90 degrees")
    print("  movemon 180 50      - Move to 180° at 50 deg/s with live feedback")
    print("  rel 30              - Move 30 degrees from current position")
    print("  watch               - Monitor position/torque continuously")
    print("  stop                - Stop immediately")
    print("="*70 + "\n")

def main():
    """Main interactive loop"""
    print("="*70)
    print("MyActuator X10-100 Interactive Control")
    print("="*70)
    print(f"Connecting to {WAVESHARE_IP}:{WAVESHARE_PORT}...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    
    try:
        sock.connect((WAVESHARE_IP, WAVESHARE_PORT))
        print("✓ Connected!")
        print(f"Motor ID: {MOTOR_ID} (CAN ID: 0x{MOTOR_CAN_ID:03X})")
        print_help()
        
        while True:
            try:
                cmd = input(">> ").strip().lower()
                
                if not cmd:
                    continue
                    
                parts = cmd.split()
                command = parts[0]
                
                if command == 'quit' or command == 'exit':
                    print("Disabling motor before exit...")
                    motor_disable(sock)
                    break
                    
                elif command == 'help':
                    print_help()
                    
                elif command == 'enable':
                    if motor_enable(sock):
                        print("✓ Motor enabled")
                    else:
                        print("✗ Failed to enable motor")
                        
                elif command == 'disable':
                    if motor_disable(sock):
                        print("✓ Motor disabled")
                    else:
                        print("✗ Failed to disable motor")
                        
                elif command == 'zero':
                    if set_zero(sock):
                        # Read current position and set as zero offset
                        state = get_motor_state(sock, apply_zero=False)
                        if state:
                            global zero_offset
                            zero_offset = state['position_abs']
                            print(f"✓ Zero set (offset: {zero_offset:.2f}°, absolute: {state['position_abs']:.2f}°)")
                        else:
                            print("✓ Zero position set")
                    else:
                        print("✗ Failed to set zero")
                        
                elif command == 'status':
                    state = get_motor_state(sock)
                    if state:
                        print(f"  Position: {state['position']:8.2f}° (raw: {state['position_raw']})")
                        print(f"  Speed:    {state['speed']:8.2f} deg/s")
                        print(f"  Torque:   {state['torque']:8.2f} Nm")
                        print(f"  Temp:     {state['temp']:8d}°C")
                        if zero_offset != 0:
                            print(f"  (Zero offset: {zero_offset:.2f}°, Absolute: {state['position_abs']:.2f}°)")
                    else:
                        print("✗ Failed to read status")
                        
                elif command == 'move':
                    if len(parts) < 2:
                        print("Usage: move <degrees> [speed]")
                    else:
                        try:
                            position = float(parts[1])
                            speed = float(parts[2]) if len(parts) > 2 else 100.0
                            if move_to_position(sock, position, speed):
                                print(f"✓ Moving to {position}° at {speed} deg/s")
                            else:
                                print("✗ Failed to send move command")
                        except ValueError:
                            print("Invalid number format")
                            
                elif command == 'movemon':
                    if len(parts) < 2:
                        print("Usage: movemon <degrees> [speed]")
                    else:
                        try:
                            position = float(parts[1])
                            speed = float(parts[2]) if len(parts) > 2 else 100.0
                            move_with_monitoring(sock, position, speed)
                        except ValueError:
                            print("Invalid number format")
                            
                elif command == 'rel' or command == 'relative':
                    if len(parts) < 2:
                        print("Usage: rel <degrees> [speed]")
                    else:
                        try:
                            offset = float(parts[1])
                            speed = float(parts[2]) if len(parts) > 2 else 100.0
                            
                            # Get current position
                            state = get_motor_state(sock)
                            if state:
                                target = state['position'] + offset
                                abs_target = target + zero_offset
                                print(f"Commanding: {offset:+.1f}° relative")
                                print(f"  Current: {state['position']:.1f}° → Target: {target:.1f}° (absolute: {abs_target:.1f}°)")
                                if move_to_position(sock, target, speed):
                                    print(f"✓ Moving {offset:+.1f}° at {speed} deg/s")
                                else:
                                    print("✗ Failed to send move command")
                            else:
                                print("✗ Failed to read current position")
                        except ValueError:
                            print("Invalid number format")
                            
                elif command == 'speed':
                    if len(parts) < 2:
                        print("Usage: speed <deg/s>")
                    else:
                        try:
                            speed_val = float(parts[1])
                            if set_speed(sock, speed_val):
                                print(f"✓ Speed set to {speed_val} deg/s")
                            else:
                                print("✗ Failed to set speed")
                        except ValueError:
                            print("Invalid number format")
                            
                elif command == 'stop':
                    if set_speed(sock, 0.0):
                        print("✓ Motor stopped")
                    else:
                        print("✗ Failed to stop motor")
                        
                elif command == 'watch':
                    print("Monitoring motor status (Press Ctrl+C to stop)...")
                    print("Position   Raw      Speed      Torque    Temp")
                    print("-" * 55)
                    try:
                        while True:
                            state = get_motor_state(sock)
                            if state:
                                print(f"\r{state['position']:7.2f}°  {state['position_abs']:6.2f}°  {state['speed']:7.2f} dps  "
                                      f"{state['torque']:6.2f} Nm  {state['temp']:3d}°C", end='', flush=True)
                            time.sleep(1.0)
                    except KeyboardInterrupt:
                        print("\n✓ Monitoring stopped")
                            
                else:
                    print(f"Unknown command: {command}. Type 'help' for commands.")
                    
            except KeyboardInterrupt:
                print("\n\nCtrl+C detected. Disabling motor...")
                motor_disable(sock)
                break
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sock.close()
        print("Disconnected")

if __name__ == "__main__":
    main()
