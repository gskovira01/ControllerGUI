"""
Example TIM Client - Test TCP Connection
=========================================

Simple TCP client for testing the TIM Motion Service locally.

Usage:
    python examples/client_test.py
"""

import socket
import time

# Configuration
TIM_HOST = "127.0.0.1"  # localhost (or 192.168.1.100 for remote iPC400)
TIM_PORT = 503
TIMEOUT = 2.0


def send_command(sock, command):
    """Send command and receive response."""
    print(f"→ {command}")
    sock.sendall(f"{command}\r\n".encode())
    
    try:
        response = sock.recv(256).decode().strip()
        print(f"← {response}\n")
        return response
    except socket.timeout:
        print("← [timeout]\n")
        return None


def main():
    """Run test sequence."""
    print("=" * 60)
    print("TIM Motion Service - Test Client")
    print("=" * 60)
    print(f"Connecting to {TIM_HOST}:{TIM_PORT}...")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((TIM_HOST, TIM_PORT))
        print("Connected!\n")
    except Exception as e:
        print(f"ERROR: Could not connect: {e}")
        return
    
    try:
        # Test sequence
        print("[AXIS A - Enable, Move, Query]")
        send_command(sock, "SH A")             # Enable
        time.sleep(0.2)
        send_command(sock, "PA A=45")          # Move to 45 degrees
        time.sleep(0.2)
        send_command(sock, "SP A=100")         # Set speed to 100 DPS
        time.sleep(0.2)
        send_command(sock, "MG _RPA")          # Query position
        time.sleep(0.2)
        
        print("[AXIS B - Enable, Relative Move]")
        send_command(sock, "SH B")             # Enable
        time.sleep(0.2)
        send_command(sock, "PR B=10")          # Move +10 degrees
        time.sleep(0.2)
        send_command(sock, "MG _RPB")          # Query position
        time.sleep(0.2)
        
        print("[AXIS A - Stop, Disable, Clear Position]")
        send_command(sock, "ST A")             # Stop
        time.sleep(0.2)
        send_command(sock, "MO A")             # Disable
        time.sleep(0.2)
        send_command(sock, "DP A")             # Clear position
        time.sleep(0.2)
        
        print("[AXIS E (ClearCore) - Enable, Move]")
        send_command(sock, "SH E")             # Enable
        time.sleep(0.2)
        send_command(sock, "PA E=30")          # Move to 30 degrees
        time.sleep(0.2)
        send_command(sock, "MG _RPE")          # Query position
        time.sleep(0.2)
        send_command(sock, "MO E")             # Disable
        time.sleep(0.2)
        
        print("=" * 60)
        print("Test sequence complete!")
        print("=" * 60)
    
    finally:
        sock.close()
        print("Disconnected")


if __name__ == '__main__':
    main()
