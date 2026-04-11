"""
Scan for MyActuator motors on different CAN IDs
"""

import socket
import struct
import time

WAVESHARE_IP = '192.168.0.7'
WAVESHARE_PORT = 20001

def create_can_frame(can_id, data):
    dlc = len(data)
    return struct.pack('<IB', can_id, dlc) + data + b'\x00' * (8 - dlc)

def scan_motor_id(sock, motor_id):
    """Try to ping a motor at specific ID"""
    can_id = 0x140 + motor_id
    # Send read state command
    data = bytes([0x9C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
    frame = create_can_frame(can_id, data)
    
    sock.send(frame)
    sock.settimeout(0.3)
    
    try:
        response = sock.recv(1024)
        if len(response) > 0:
            return True, response
    except socket.timeout:
        pass
    
    return False, None

print("Scanning for MyActuator motors (ID 1-32)...")
print(f"Connected to {WAVESHARE_IP}:{WAVESHARE_PORT}\n")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((WAVESHARE_IP, WAVESHARE_PORT))

found = []

for motor_id in range(1, 33):
    print(f"Scanning ID {motor_id}...", end=' ')
    success, response = scan_motor_id(sock, motor_id)
    
    if success:
        print(f"✓ FOUND! Response: {response.hex()}")
        found.append(motor_id)
    else:
        print("✗")
    
    time.sleep(0.05)

sock.close()

print("\n" + "="*70)
if found:
    print(f"Found {len(found)} motor(s) at ID(s): {found}")
else:
    print("No motors found. Check:")
    print("  - Motor power")
    print("  - CAN bus wiring")
    print("  - CAN termination resistor (120Ω)")
    print("  - Frame format might be wrong")
