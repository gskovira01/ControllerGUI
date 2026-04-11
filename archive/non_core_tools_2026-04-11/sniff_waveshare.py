"""
Waveshare TCP Packet Sniffer - Self-Contained Version
Sends periodic commands and displays request/response pairs
"""

import socket
import time
import struct
import threading

WAVESHARE_IP = '192.168.0.7'
WAVESHARE_PORT = 20001
MOTOR_ID = 1  # Change this if your motor has a different ID
POLL_INTERVAL = 1.0  # Send command every second

# Command definitions
CMD_READ_MULTI_TURN_ANGLE = 0x92
CMD_READ_STATUS = 0x9C
CMD_READ_SINGLE_ANGLE = 0x94

def format_can_frame(data):
    """Parse and format a CAN frame (Waveshare 2-CH format)"""
    if len(data) >= 13:
        # Waveshare format: DLC (1 byte) + CAN_ID (4 bytes, big endian) + Data (8 bytes)
        dlc = data[0]
        can_id = struct.unpack('>I', data[1:5])[0]
        payload = data[5:5+dlc]
        
        # Decode motor ID from CAN ID
        if can_id >= 0x240 and can_id <= 0x25F:
            motor_id = can_id - 0x240
            direction = "RESPONSE"
        elif can_id >= 0x140 and can_id <= 0x15F:
            motor_id = can_id - 0x140
            direction = "COMMAND"
        else:
            motor_id = "?"
            direction = "UNKNOWN"
        
        result = f"{direction} Motor_{motor_id} | CAN_ID=0x{can_id:03X} DLC={dlc} | Data=[{payload.hex()}]"
        
        # Try to decode payload
        if dlc >= 1:
            cmd = payload[0]
            if cmd == 0x92:
                result += " | READ_MULTI_TURN"
            elif cmd == 0x9C:
                result += " | READ_STATUS"
            elif cmd == 0x94:
                result += " | READ_SINGLE_ANGLE"
            
            # Decode response data if available
            if dlc >= 7 and direction == "RESPONSE":
                try:
                    angle_raw = struct.unpack('<i', payload[1:5])[0]
                    angle_deg = angle_raw * 0.01  # Convert to degrees
                    result += f" | Angle={angle_deg:.2f}°"
                except:
                    pass
        
        return result
    return f"INVALID ({len(data)} bytes): {data.hex()}"

def create_can_frame(can_id, data):
    """Create a CAN frame for Waveshare 2-CH-CAN-TO-ETH converter"""
    dlc = len(data)
    # Pack: DLC (1 byte) + CAN_ID (4 bytes, big endian) + Data (8 bytes)
    frame = struct.pack('B', dlc) + struct.pack('>I', can_id) + data + b'\x00' * (8 - dlc)
    return frame

def receive_thread(sock, stop_event, response_count):
    """Thread to continuously receive packets"""
    sock.settimeout(0.1)
    
    while not stop_event.is_set():
        try:
            data = sock.recv(1024)
            if len(data) > 0:
                response_count[0] += 1
                timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
                print(f"[{timestamp}] ← {format_can_frame(data)}")
        except socket.timeout:
            continue
        except Exception as e:
            if not stop_event.is_set():
                print(f"Receive error: {e}")
            break

def send_thread(sock, stop_event, command_count):
    """Thread to periodically send test commands"""
    commands = [
        (CMD_READ_MULTI_TURN_ANGLE, "Multi-turn angle"),
        (CMD_READ_STATUS, "Status"),
        (CMD_READ_SINGLE_ANGLE, "Single angle"),
    ]
    cmd_index = 0
    
    time.sleep(1)  # Wait before starting
    
    while not stop_event.is_set():
        try:
            # Cycle through different commands
            cmd_byte, cmd_name = commands[cmd_index]
            cmd_index = (cmd_index + 1) % len(commands)
            
            can_id = 0x140 + MOTOR_ID
            cmd_data = bytes([cmd_byte, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            frame = create_can_frame(can_id, cmd_data)
            
            sock.send(frame)
            command_count[0] += 1
            timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
            print(f"[{timestamp}] → {format_can_frame(frame)}")
            
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            if not stop_event.is_set():
                print(f"Send error: {e}")
            break

print("="*80)
print("Waveshare TCP Packet Sniffer - Self-Contained Mode")
print("="*80)
print(f"Target: {WAVESHARE_IP}:{WAVESHARE_PORT}")
print(f"Motor ID: {MOTOR_ID}")
print(f"Poll Interval: {POLL_INTERVAL}s")
print("="*80)
print(f"\nConnecting...")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5.0)

try:
    sock.connect((WAVESHARE_IP, WAVESHARE_PORT))
    print("✓ Connected!")
    print("\nStarting periodic polling... (Press Ctrl+C to stop)\n")
    
    # Start receiver and sender threads
    stop_event = threading.Event()
    response_count = [0]
    command_count = [0]
    
    receiver = threading.Thread(target=receive_thread, args=(sock, stop_event, response_count))
    sender = threading.Thread(target=send_thread, args=(sock, stop_event, command_count))
    
    receiver.daemon = True
    sender.daemon = True
    
    receiver.start()
    sender.start()
    
    # Keep main thread alive and show stats periodically
    start_time = time.time()
    while True:
        time.sleep(5)
        elapsed = time.time() - start_time
        print(f"\n--- Stats: {int(elapsed)}s elapsed | Commands sent: {command_count[0]} | Responses: {response_count[0]} ---\n")
            
except KeyboardInterrupt:
    print("\n\nStopped by user")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    stop_event.set()
    time.sleep(0.2)
    sock.close()
    print("Disconnected")
