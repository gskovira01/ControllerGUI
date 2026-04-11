"""
Waveshare TCP Bridge with Packet Display
This creates a local server that forwards to Waveshare and displays all traffic.

Usage:
1. Run this script
2. Configure MyActuator software to connect to 127.0.0.1:20001
3. All traffic will be displayed and forwarded to the real Waveshare

"""

import socket
import struct
import time
import threading
import sys

WAVESHARE_IP = '192.168.0.7'
WAVESHARE_PORT = 20001
LOCAL_IP = '127.0.0.1'
LOCAL_PORT = 20001

def format_can_frame(data):
    """Parse and format a CAN frame (Waveshare 2-CH format)"""
    if len(data) >= 13:
        # Waveshare format: DLC (1 byte) + CAN_ID (4 bytes, big endian) + Data (8 bytes)
        dlc = data[0]
        can_id = struct.unpack('>I', data[1:5])[0]
        payload = data[5:5+dlc]
        return f"CAN_ID=0x{can_id:03X} DLC={dlc} Data=[{payload.hex()}]"
    return f"RAW ({len(data)} bytes): {data.hex()}"

def client_to_waveshare(client_sock, waveshare_sock, client_addr):
    """Forward packets from client to Waveshare"""
    try:
        while True:
            data = client_sock.recv(1024)
            if not data:
                break
            
            timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
            print(f"\n[{timestamp}] CLIENT→WAVESHARE:")
            print(f"  {format_can_frame(data)}")
            
            waveshare_sock.send(data)
    except Exception as e:
        print(f"Client→Waveshare error: {e}")

def waveshare_to_client(client_sock, waveshare_sock):
    """Forward packets from Waveshare to client"""
    try:
        waveshare_sock.settimeout(0.5)
        while True:
            try:
                data = waveshare_sock.recv(1024)
                if not data:
                    break
                
                timestamp = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
                print(f"\n[{timestamp}] WAVESHARE→CLIENT:")
                print(f"  {format_can_frame(data)}")
                
                client_sock.send(data)
            except socket.timeout:
                continue
    except Exception as e:
        print(f"Waveshare→Client error: {e}")

def handle_client(client_sock, client_addr):
    """Handle a client connection"""
    print(f"\n{'='*70}")
    print(f"Client connected from {client_addr}")
    print(f"{'='*70}")
    
    try:
        # Connect to Waveshare
        print(f"Connecting to Waveshare at {WAVESHARE_IP}:{WAVESHARE_PORT}...")
        waveshare_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        waveshare_sock.connect((WAVESHARE_IP, WAVESHARE_PORT))
        print("✓ Connected to Waveshare!")
        print("\nForwarding traffic (both directions shown below):\n")
        
        # Start bidirectional forwarding
        thread1 = threading.Thread(target=client_to_waveshare, args=(client_sock, waveshare_sock, client_addr))
        thread2 = threading.Thread(target=waveshare_to_client, args=(client_sock, waveshare_sock))
        
        thread1.daemon = True
        thread2.daemon = True
        
        thread1.start()
        thread2.start()
        
        # Wait for threads to finish
        thread1.join()
        thread2.join()
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print(f"\nClient {client_addr} disconnected")
        client_sock.close()
        try:
            waveshare_sock.close()
        except:
            pass

def main():
    print("="*70)
    print("Waveshare TCP Bridge with Packet Display")
    print("="*70)
    print(f"\nListening on {LOCAL_IP}:{LOCAL_PORT}")
    print(f"Forwarding to {WAVESHARE_IP}:{WAVESHARE_PORT}")
    print("\nConfigure MyActuator software to connect to:")
    print(f"  IP: {LOCAL_IP}")
    print(f"  Port: {LOCAL_PORT}")
    print("\nWaiting for client connection...\n")
    
    # Create server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((LOCAL_IP, LOCAL_PORT))
        server.listen(1)
        
        while True:
            client_sock, client_addr = server.accept()
            # Handle one client at a time
            handle_client(client_sock, client_addr)
            
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server.close()

if __name__ == "__main__":
    main()
