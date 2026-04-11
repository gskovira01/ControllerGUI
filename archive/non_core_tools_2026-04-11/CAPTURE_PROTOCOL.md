# Capturing MyActuator Protocol with Wireshark

## Steps to discover the correct frame format:

### 1. Install Wireshark (if not installed)
Download from: https://www.wireshark.org/download.html

### 2. Start Wireshark
- Run Wireshark as Administrator
- Select your Ethernet adapter connected to Waveshare
- Start capturing

### 3. Filter for Waveshare traffic
In the filter box, type:
```
ip.addr == 192.168.0.7 and udp
```

### 4. Run MyActuator Software
- Open MC_300.exe
- Connect to the motor
- Send a simple command (like read status or enable motor)
- Move the motor slightly

### 5. Stop capture and analyze
- Stop Wireshark capture
- Look at the UDP packets sent TO 192.168.0.7
- Right-click a packet → Follow → UDP Stream
- Note the exact byte format

### 6. Key things to find:
- **Destination port** (might not be 1000)
- **Frame header** (if any, like 0xAA 0x55)
- **How CAN ID is encoded** (position in frame, byte order)
- **Complete frame structure**

### 7. Share the data
Copy one example packet's hex data and we'll update the Python script!

## Alternative: Check Waveshare documentation
Look for:
- User manual PDF
- Configuration guide showing UDP frame format
- Example code (might be in C or Python)
