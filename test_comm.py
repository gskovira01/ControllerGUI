import configparser
from communications import ControllerComm # pyright: ignore[reportMissingImports]
import serial.tools.list_ports


config = configparser.ConfigParser()
config.read('controller_config.ini')

controller_type = config['Controller']['type'].split(';')[0].strip()

if controller_type == 'CommMode1':
    galil_config = {'address': config['CommMode1']['address']}
    comm = ControllerComm(mode='CommMode1', galil_config=galil_config)
elif controller_type == 'CommMode2':
    # Try the port from the ini file first
    ini_port = config['CommMode2']['port']
    serial_config = {
        'port': ini_port,
        'baudrate': int(config['CommMode2']['baudrate']),
        'timeout': float(config['CommMode2']['timeout'])
    }
    comm = ControllerComm(mode='CommMode2', serial_config=serial_config)
    # Test if the port opened successfully
    if not hasattr(comm, 'ser') or comm.ser is None or not comm.ser.is_open:
        print(f"Failed to open port '{ini_port}'. Listing available COM ports:")
        import serial.tools.list_ports # pyright: ignore[reportMissingModuleSource]
        ports = list(serial.tools.list_ports.comports())
        for idx, port in enumerate(ports):
            print(f"[{idx}] {port.device}: {port.description}")
        if ports:
            selection = input("Select COM port by number (or press Enter to abort): ")
            if selection.isdigit() and int(selection) < len(ports):
                selected_port = ports[int(selection)].device
                # Update the ini file with the selected port
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
elif controller_type == 'CommMode3':
    udp_config = {
        'ip1': config['CommMode3']['ip1'],
        'port1': int(config['CommMode3']['port1']),
        'local_port': int(config['CommMode3']['local_port'])
    }
    comm = ControllerComm(mode='CommMode3', udp_config=udp_config)
else:
    raise ValueError(f"Unknown controller type: {controller_type}")

# Connection check: Query Galil version if using CommMode2
if controller_type == 'CommMode2':
    # Galil version query is usually "MG _HW" or "MG _BN" or "MG _VR"; try "MG _BN" for board name/version
    comm.send_command('MG _BN')
    version_response = comm.receive_response(timeout=2.0)
    if version_response:
        print(f"Galil connection established. Controller version: {version_response}")
    else:
        print("No response from Galil controller. Connection may not be established.")

# Example usage:
comm.send_command('MG _RPA')  # Or 'CMD:REQUEST_BUTTON_STATES' for ClearCore
response = comm.receive_response(timeout=2.0)
print("Received:", response)
comm.close()
