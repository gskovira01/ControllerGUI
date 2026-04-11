
import configparser
import os
from communications import ControllerComm

class InitializeController:
    def __init__(self, ini_path='controller_config.ini'):
        self.ini_path = ini_path
        self.controller_type = None
        self.comm_config = None
        self.comm = None
        self._read_ini()
        self._create_comm()

    def _read_ini(self):
        config = configparser.ConfigParser()
        if not os.path.exists(self.ini_path):
            raise FileNotFoundError(f"INI file not found: {self.ini_path}")
        config.read(self.ini_path)
        try:
            self.controller_type = config['Controller']['type'].strip()
        except Exception:
            self.controller_type = None
        if self.controller_type == 'CommMode1' and config.has_section('CommMode1'):
            self.comm_config = dict(config.items('CommMode1'))
        elif self.controller_type == 'CommMode2' and config.has_section('CommMode2'):
            self.comm_config = dict(config.items('CommMode2'))
        elif self.controller_type == 'CommMode3' and config.has_section('CommMode3'):
            self.comm_config = dict(config.items('CommMode3'))
        elif self.controller_type == 'CommMode4' and config.has_section('CommMode4'):
            self.comm_config = dict(config.items('CommMode4'))
        else:
            self.comm_config = {}

    def _create_comm(self):
        if self.controller_type == 'CommMode1':
            self.comm = ControllerComm(mode='CommMode1', galil_config=self.comm_config)
        elif self.controller_type == 'CommMode2':
            # Convert config values to correct types
            if 'baudrate' in self.comm_config:
                self.comm_config['baudrate'] = int(self.comm_config['baudrate'])
            if 'timeout' in self.comm_config:
                self.comm_config['timeout'] = float(self.comm_config['timeout'])
            self.comm = ControllerComm(mode='CommMode2', serial_config=self.comm_config)
        elif self.controller_type == 'CommMode3':
            if 'port1' in self.comm_config:
                self.comm_config['port1'] = int(self.comm_config['port1'])
            if 'local_port' in self.comm_config:
                self.comm_config['local_port'] = int(self.comm_config['local_port'])
            self.comm = ControllerComm(mode='CommMode3', udp_config=self.comm_config)
        elif self.controller_type == 'CommMode4':
            # Convert config values to correct types for RMP
            if 'use_hardware' in self.comm_config:
                # Convert string to boolean
                self.comm_config['use_hardware'] = self.comm_config['use_hardware'].lower() == 'true'
            if 'num_axes' in self.comm_config:
                self.comm_config['num_axes'] = int(self.comm_config['num_axes'])
            self.comm = ControllerComm(mode='CommMode4', rmp_config=self.comm_config)
        else:
            raise ValueError('Unknown or unsupported controller type.')

    def query_all_axes(self):
        AXIS_LETTERS = ['A','B','C','D','E','F','G','H']
        fields = ['velocity', 'acceleration', 'deceleration', 'abs_pos_setpoint', 'rel_pos_setpoint', 'actual_pos']
        commands = {
            'velocity': 'MG _SP{}',
            'acceleration': 'MG _AC{}',
            'deceleration': 'MG _DC{}',
            'abs_pos_setpoint': 'MG _PA{}',
            'rel_pos_setpoint': 'MG _PR{}',
            'actual_pos': 'MG _RP{}',
        }
        import re
        results = {}
        for i, axis in enumerate(AXIS_LETTERS, 1):
            axis_results = {}
            for field in fields:
                cmd = commands[field].format(axis)
                print(f"Querying Axis {axis} Field {field}: {cmd}")
                resp = self.comm.send_command(cmd)
                print(f"Axis {axis} Field {field}: Raw response: {repr(resp)}")
                match = re.search(r'(-?\d+(?:\.\d+)?)', str(resp))
                axis_results[field] = float(match.group(1)) if match else None
            results[axis] = axis_results
        return results

if __name__ == "__main__":
    ic = InitializeController()
    print(f"Controller type: {ic.controller_type}")
    print(f"Comm config: {ic.comm_config}")
    all_axis_values = ic.query_all_axes()
    import pprint
    pprint.pprint(all_axis_values)
