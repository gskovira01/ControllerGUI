"""
Test Waveshare CAN-to-ETH with TCP connection
Some Waveshare models use TCP instead of UDP
"""

import socket
import struct
import time

WAVESHARE_IP = '192.168.0.7'
MOTOR_ID = 1
MOTOR_CAN_ID = 0x140 + MOTOR_ID

def create_can_frame(can_id, data):
    """Try simple CAN frame format"""
    dlc = len(data)
    # Standard CAN frame: ID (11-bit in 4 bytes) + DLC + Data
    return struct.pack('<IB', can_id, dlc) + data + b'\x00' * (8 - dlc)

print("Testing TCP connection to Waveshare...")
print(f"IP: {WAVESHARE_IP}")
print("\nTrying common ports...")

# Common TCP ports for CAN-to-ETH converters
test_ports = [23, 4001, 5000, 8080, 1000, 2000, 60000]

for port in test_ports:
    print(f"\n--- Testing port {port} ---")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect((WAVESHARE_IP, port))
        print(f"✓ TCP connection established on port {port}!")
        
        # Try sending a simple command (read PID - 0x30)
        cmd_data = bytes([0x30, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        frame = create_can_frame(MOTOR_CAN_ID, cmd_data)
        
        print(f"Sending frame: {frame.hex()}")
        sock.send(frame)
        
        # Try to receive
        sock.settimeout(1.0)
        try:
            response = sock.recv(1024)
            print(f"✓✓ RECEIVED RESPONSE: {response.hex()}")
            print(f"Response length: {len(response)} bytes")
        except socket.timeout:
            print("No response received")
        
        sock.close()
        
    except ConnectionRefusedError:
        print(f"✗ Connection refused on port {port}")
    except socket.timeout:
        print(f"✗ Timeout on port {port}")
    except Exception as e:
        print(f"✗ Error: {e}")

print("\n" + "="*70)
print("If a port connected, that's your Waveshare port!")
print("If you got a response, the frame format is correct!")
