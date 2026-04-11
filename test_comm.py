import configparser
from communications import ControllerComm # pyright: ignore[reportMissingImports]
import serial.tools.list_ports  # pyright: ignore[reportMissingImports]

config = configparser.ConfigParser()
config.read('controller_config.ini')

controller_type = config['Controller']['type'].split(';')[0].strip()

if controller_type == 'CommMode2':
    ini_port = config['CommMode2']['port']
    serial_config = {
        'port': ini_port,
        'baudrate': int(config['CommMode2']['baudrate']),
        'timeout': float(config['CommMode2']['timeout']),
        'parity': config['CommMode2'].get('parity', 'N'),
        'stopbits': float(config['CommMode2'].get('stopbits', 1.0)),
        'rtscts': True
    }
    comm = ControllerComm(mode='CommMode2', serial_config=serial_config)
    # Test if the port opened successfully
    if not hasattr(comm, 'ser') or comm.ser is None or not comm.ser.is_open:
        print(f"Failed to open port '{ini_port}'. Listing available COM ports:")
        ports = list(serial.tools.list_ports.comports())
        for idx, port in enumerate(ports):
            print(f"[{idx}] {port.device}: {port.description}")
        if ports:
            selection = input("Select COM port by number (or press Enter to abort): ")
            if selection.isdigit() and int(selection) < len(ports):
                selected_port = ports[int(selection)].device
                config['CommMode2']['port'] = selected_port
                with open('controller_config.ini', 'w') as configfile:
                    config.write(configfile)
                serial_config['port'] = selected_port
                comm = ControllerComm(mode='CommMode2', serial_config=serial_config)
            else:
                print("No valid port selected. Exiting.")
                exit(1)
        else:
            print("No COM ports found. Exiting.")
            exit(1)
    # Add a short delay after opening the port
    import time
    time.sleep(0.5)
elif controller_type == 'CommMode1':
    galil_config = {'address': config['CommMode1']['address']}
    comm = ControllerComm(mode='CommMode1', galil_config=galil_config)
elif controller_type == 'CommMode3':
    udp_config = {
        'ip1': config['CommMode3']['ip1'],
        'port1': int(config['CommMode3']['port1']),
        'local_port': int(config['CommMode3']['local_port'])
    }
    comm = ControllerComm(mode='CommMode3', udp_config=udp_config)
else:
    raise ValueError(f"Unknown controller type: {controller_type}")


# Diagnostic: Try multiple version/query commands and print all responses
if controller_type == 'CommMode2':
    # Send CW2 to ensure unsolicited messages are readable
    # print("Sending: CW2 (set unsolicited messages to readable)")
    #c omm.send_command('CW2')
    # Enable echo for diagnostics
    print("Sending: EO 1 (enable echo)")
    comm.send_command('EO 1')
    commands = [
        'MG _RPA',      # Query controller time
    ]
    for cmd in commands:
        print(f"Sending: {cmd}")
        response = comm.send_command(cmd)
        # Flush serial input buffer before sending command
        if hasattr(comm, 'ser') and comm.ser is not None:
            comm.ser.reset_input_buffer()
        print("--- Raw Controller Response ---")
        found_valid = False
        raw_resp = None
        import re
        for attempt in range(10):
            resp = comm.send_command(cmd) if attempt == 0 else comm.receive_response(timeout=0.5)
            if resp is None:
                continue
            resp = str(resp).strip()
            # Echoed command detection: if response matches the sent command
            if resp == cmd:
                print(f"Echoed Command: {resp}")
                continue
            if resp == ':' or not resp:
                continue
            # Check for colon at end of response
            if resp.endswith(':'):
                print(f"Colon found at end of response: {resp}")
            float_matches = re.findall(r'-?\d+\.\d+', resp)
            if float_matches:
                val = float(float_matches[0])
                print(f"Value: {val}")
                raw_resp = resp
                found_valid = True
                break
        if not found_valid:
            print("No valid response found.")
        # Flush serial input buffer after reading response
        if hasattr(comm, 'ser') and comm.ser is not None:
            comm.ser.reset_input_buffer()
        print("--- End Controller Response ---")
    comm.close()
