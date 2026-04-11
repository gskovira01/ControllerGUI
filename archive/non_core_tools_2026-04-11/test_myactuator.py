"""
================================================================================
MyActuator X10-100 Test Script via Waveshare CAN-to-ETH Converter
================================================================================

This script tests the connection to a MyActuator X10-100 motor through
a Waveshare 20ch CAN-to-ETH converter using TCP protocol.

Hardware Setup:
    PC <--Ethernet--> Waveshare CAN-to-ETH <--2-wire CAN--> MyActuator X10-100

Waveshare Settings:
    - IP: 192.168.0.7
    - Port: 20001 (TCP Server for CAN1)
    - Baud: 1Mbps
    
MyActuator Protocol:
    - Send CAN ID: 0x140 + Motor_ID
    - Reply CAN ID: 0x240 + Motor_ID

================================================================================
"""

import socket
import struct
import time

# ============================================================================
# CONFIGURATION - ADJUST THESE FOR YOUR SETUP
# ============================================================================
WAVESHARE_IP = '192.168.0.7'        # IP address of Waveshare converter
WAVESHARE_PORT = 20001               # TCP Server port for CAN1
MOTOR_ID = 1                         # Motor ID (1-32)
MOTOR_CAN_ID = 0x140 + MOTOR_ID      # CAN ID = 0x140 + ID (single motor command)
MOTOR_REPLY_ID = 0x240 + MOTOR_ID    # Reply ID = 0x240 + ID

# ============================================================================
# MyActuator Protocol Commands (X10 Series)
# ============================================================================
CMD_MOTOR_OFF = 0x80        # Turn motor off (brake)
CMD_MOTOR_ON = 0x88         # Turn motor on (release brake)
CMD_ZERO_POSITION = 0x19    # Set current position as zero
CMD_POSITION_CONTROL = 0xA4 # Position control mode
CMD_SPEED_CONTROL = 0xA2    # Speed control mode
CMD_REQUEST_STATE = 0x9C    # Request motor state

# ============================================================================
# Helper Functions
# ============================================================================

def create_can_frame(can_id, data):
    """
    Create a CAN frame for Waveshare 2-CH-CAN-TO-ETH converter
    
    Correct format (13 bytes total):
    - Byte 1: Frame control (DLC for data frame, 0x08 = 8 bytes)
    - Bytes 2-5: CAN ID (4 bytes, big endian)
    - Bytes 6-13: Data (8 bytes)
    
    Example: 08 00 00 01 41 9C 00 00 00 00 00 00 00
    """
    dlc = len(data)
    # Pack: DLC (1 byte) + CAN_ID (4 bytes, big endian) + Data (8 bytes)
    frame = struct.pack('B', dlc) + struct.pack('>I', can_id) + data + b'\x00' * (8 - dlc)
    return frame

def send_can_message(sock, can_id, data):
    """Send a CAN message via TCP to Waveshare converter"""
    frame = create_can_frame(can_id, data)
    sock.send(frame)
    print(f"Sent CAN ID 0x{can_id:03X}: {data.hex()}")
    print(f"  Full frame ({len(frame)} bytes): {frame.hex()}")

def receive_can_message(sock, timeout=1.0):
    """Receive a CAN message from Waveshare converter via TCP"""
    sock.settimeout(timeout)
    try:
        data = sock.recv(1024)
        if len(data) == 0:
            print("Connection closed by remote host")
            return None, None
            
        print(f"Raw received ({len(data)} bytes): {data.hex()}")
        
        # Waveshare format: DLC (1 byte) + CAN_ID (4 bytes, big endian) + Data (8 bytes)
        if len(data) >= 13:
            dlc = data[0] & 0x0F  # Lower nibble is DLC (ignore remote frame flag)
            can_id = struct.unpack('>I', data[1:5])[0]  # Big endian
            payload = data[5:5+dlc]
            print(f"Received CAN ID 0x{can_id:03X}: {payload.hex()}")
            return can_id, payload
        return None, None
    except socket.timeout:
        print("No response received (timeout)")
        return None, None
    except (ConnectionResetError, OSError) as e:
        print(f"Connection error: {e}")
        return None, None

# ============================================================================
# Motor Control Functions
# ============================================================================

def motor_enable(sock):
    """Enable motor (release brake)"""
    print("\n=== Enabling Motor ===")
    data = bytes([CMD_MOTOR_ON, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can_message(sock, MOTOR_CAN_ID, data)
    time.sleep(0.1)
    return receive_can_message(sock)

def motor_disable(sock):
    """Disable motor (engage brake)"""
    print("\n=== Disabling Motor ===")
    data = bytes([CMD_MOTOR_OFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    try:
        send_can_message(sock, MOTOR_CAN_ID, data)
        time.sleep(0.1)
        return receive_can_message(sock, timeout=0.5)
    except Exception as e:
        print(f"Error during disable: {e}")
        return None, None

def set_zero_position(sock):
    """Set current position as zero"""
    print("\n=== Setting Zero Position ===")
    data = bytes([CMD_ZERO_POSITION, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can_message(sock, MOTOR_CAN_ID, data)
    time.sleep(0.1)
    return receive_can_message(sock)

def request_motor_state(sock):
    """Request motor state (position, velocity, torque)"""
    print("\n=== Requesting Motor State ===")
    data = bytes([CMD_REQUEST_STATE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    send_can_message(sock, MOTOR_CAN_ID, data)
    time.sleep(0.1)
    return receive_can_message(sock)

def move_to_position(sock, position_deg, max_speed=10.0):
    """
    Move motor to specified position
    
    Args:
        position_deg: Target position in degrees (-360 to 360)
        max_speed: Maximum speed in deg/s
    """
    print(f"\n=== Moving to {position_deg}° ===")
    
    # Convert to motor units (X10 uses 0.01° per count)
    position_counts = int(position_deg * 100)
    speed_counts = int(max_speed * 100)
    
    # Pack data: position (4 bytes), speed (2 bytes)
    data = struct.pack('<ihBB', position_counts, speed_counts, 0x00, 0x00)
    data = bytes([CMD_POSITION_CONTROL]) + data[:7]
    
    send_can_message(sock, MOTOR_CAN_ID, data)
    time.sleep(0.1)
    return receive_can_message(sock)

# ============================================================================
# Main Test Sequence
# ============================================================================

def main():
    """Run motor test sequence"""
    
    print("="*80)
    print("MyActuator X10-100 Connection Test")
    print("="*80)
    print(f"Waveshare IP: {WAVESHARE_IP}:{WAVESHARE_PORT} (TCP)")
    print(f"Motor ID: {MOTOR_ID}")
    print(f"Send CAN ID: 0x{MOTOR_CAN_ID:03X}")
    print(f"Reply CAN ID: 0x{MOTOR_REPLY_ID:03X}")
    print("="*80)
    
    # Create TCP socket and connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    
    try:
        print(f"\nConnecting to Waveshare...")
        sock.connect((WAVESHARE_IP, WAVESHARE_PORT))
        print("✓ TCP connection established!\n")
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sock.close()
        return
    
    try:
        # Test 1: Request motor state
        request_motor_state(sock)
        
        # Test 2: Enable motor
        motor_enable(sock)
        time.sleep(0.5)
        
        # Test 3: Set zero position
        set_zero_position(sock)
        time.sleep(0.5)
        
        # Test 4: Small movement test
        print("\n" + "="*80)
        print("Starting movement test...")
        print("="*80)
        
        # Move to 30 degrees
        move_to_position(sock, 30.0, max_speed=20.0)
        time.sleep(2)
        
        # Check position
        request_motor_state(sock)
        time.sleep(1)
        
        # Move back to 0
        move_to_position(sock, 0.0, max_speed=20.0)
        time.sleep(2)
        
        # Final state check
        request_motor_state(sock)
        
        print("\n" + "="*80)
        print("Test complete! If motor moved, connection is working.")
        print("="*80)
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        # Disable motor before exit
        print("\nDisabling motor...")
        motor_disable(sock)
        sock.close()
        print("Socket closed.")

if __name__ == "__main__":
    print("\nIMPORTANT: Make sure your PC IP is on the same subnet as the Waveshare!")
    print("Example: If Waveshare is 192.168.0.7, PC should be 192.168.0.x")
    input("\nPress Enter to start test (or Ctrl+C to cancel)...")
    main()
