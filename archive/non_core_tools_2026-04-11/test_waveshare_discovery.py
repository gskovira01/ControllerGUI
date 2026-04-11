"""
Waveshare CAN-to-ETH Discovery Script
Tests different ports and frame formats to find the right configuration
"""

import socket
import struct
import time

WAVESHARE_IP = '192.168.0.7'
TEST_PORTS = [1000, 2000, 3000, 4001, 8080, 60000, 61000]  # Common Waveshare ports
MOTOR_CAN_ID = 0x01

def test_frame_format_1(can_id, data):
    """Simple format: CAN_ID (4 bytes) + DLC + Data"""
    dlc = len(data)
    return struct.pack('<IB', can_id, dlc) + data + b'\x00' * (8 - dlc)

def test_frame_format_2(can_id, data):
    """Waveshare format with header: 0xAA55 + Type + CAN_ID + DLC + Data"""
    dlc = len(data)
    return struct.pack('<BBBBI', 0xAA, 0x55, 0x01, 0x00, can_id) + struct.pack('B', dlc) + data + b'\x00' * (8 - dlc)

def test_frame_format_3(can_id, data):
    """Alternative: Type + CAN_ID (2 bytes) + DLC + Data"""
    dlc = len(data)
    return struct.pack('<BHB', 0x01, can_id & 0x7FF, dlc) + data + b'\x00' * (8 - dlc)

def test_frame_format_4(can_id, data):
    """Raw CAN format: just data with simple header"""
    dlc = len(data)
    return struct.pack('<HB', can_id & 0x7FF, dlc) + data

def test_port_and_format(port, format_func, format_name):
    """Test a specific port and frame format"""
    print(f"\n{'='*70}")
    print(f"Testing Port {port} with {format_name}")
    print(f"{'='*70}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))
    sock.settimeout(2.0)
    
    try:
        # Send motor state request
        cmd_data = bytes([0x9C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        frame = format_func(MOTOR_CAN_ID, cmd_data)
        
        print(f"Sending to {WAVESHARE_IP}:{port}")
        print(f"Frame ({len(frame)} bytes): {frame.hex()}")
        
        sock.sendto(frame, (WAVESHARE_IP, port))
        
        # Try to receive
        try:
            data, addr = sock.recvfrom(1024)
            print(f"✓ SUCCESS! Received {len(data)} bytes from {addr}")
            print(f"  Data: {data.hex()}")
            sock.close()
            return True
        except socket.timeout:
            print("✗ No response (timeout)")
        except Exception as e:
            print(f"✗ Error: {e}")
    except Exception as e:
        print(f"✗ Send failed: {e}")
    finally:
        sock.close()
    
    return False

def main():
    print("="*70)
    print("WAVESHARE CAN-TO-ETH DISCOVERY TOOL")
    print("="*70)
    print(f"Target IP: {WAVESHARE_IP}")
    print(f"Testing {len(TEST_PORTS)} ports with 4 frame formats...")
    print()
    
    formats = [
        (test_frame_format_1, "Simple (CAN_ID + DLC + Data)"),
        (test_frame_format_2, "Waveshare Header (0xAA55 + ...)"),
        (test_frame_format_3, "Short ID (Type + 2-byte CAN_ID)"),
        (test_frame_format_4, "Raw (ID + DLC + Data)")
    ]
    
    successes = []
    
    for port in TEST_PORTS:
        for format_func, format_name in formats:
            if test_port_and_format(port, format_func, format_name):
                successes.append((port, format_name))
                print("\n" + "!"*70)
                print(f"! FOUND WORKING CONFIG: Port {port}, Format: {format_name}")
                print("!"*70)
            time.sleep(0.2)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    if successes:
        print("Working configurations found:")
        for port, fmt in successes:
            print(f"  - Port {port}: {fmt}")
    else:
        print("No working configuration found.")
        print("\nTroubleshooting suggestions:")
        print("1. Check Waveshare web interface for UDP port settings")
        print("2. Verify CAN bus is properly connected and terminated")
        print("3. Check if Waveshare is in TCP mode (not UDP)")
        print("4. Try the Waveshare configuration software")
        print("5. Consult Waveshare manual for exact frame format")

if __name__ == "__main__":
    main()
