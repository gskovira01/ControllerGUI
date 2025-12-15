# Utility: display ints without decimals, otherwise round to 1 decimal place
def format_display_value(val):
    try:
        fval = round(float(val), 1)
        if fval.is_integer():
            return str(int(fval))
        return f"{fval:.1f}"
    except Exception:
        return str(val)

"""
================================================================================
                        NUMERIC KEYPAD MODULE (CLASS)
================================================================================

Author: gskovira01
Date: December 4, 2025
Version: 1.0.0

PURPOSE:
    Provides a reusable touchscreen-friendly numeric keypad popup for value entry.
    Designed for use in PySimpleGUI applications.

USAGE:
    from numeric_keypad import NumericKeypad
    keypad = NumericKeypad(title="Enter Value", current_value=0, min_val=0, max_val=100)
    result = keypad.show()
    if result is not None:
        # Use the entered value

CLASS:
    NumericKeypad
        - __init__(title, current_value, min_val=0, max_val=54000, font=None)
        - show(): Displays the keypad popup and returns the entered value or None

================================================================================
"""

import FreeSimpleGUI as sg

# Read axis parameters from controller_config.ini
import configparser
import os
AXIS_UNITS = {}
axis_ini = configparser.ConfigParser()
axis_ini.read(os.path.join(os.path.dirname(__file__), 'controller_config.ini'))
for axis in 'ABCDEFGH':
    section = f'AXIS_{axis}'
    if section in axis_ini:
        AXIS_UNITS[axis] = {
            'min': float(axis_ini[section]['min']),
            'max': float(axis_ini[section]['max']),
            'pulses': float(axis_ini[section]['pulses']),
            'degrees': float(axis_ini[section]['degrees']),
            'scaling': float(axis_ini[section]['scaling']),
            'gearbox': float(axis_ini[section]['gearbox'])
        }

class NumericKeypad:
    def __init__(self, title, current_value, axis_letter, font=None, unit_label='', min_val=None, max_val=None):
        self.title = title
        try:
            self.current_value = round(float(current_value), 1)
        except Exception:
            self.current_value = 0.0
        self.axis_letter = axis_letter
        # Prefer explicit limits; fall back to AXIS_UNITS
        if min_val is not None and max_val is not None:
            self.min_val = min_val
            self.max_val = max_val
        elif axis_letter in AXIS_UNITS:
            self.min_val = AXIS_UNITS[axis_letter]['min']
            self.max_val = AXIS_UNITS[axis_letter]['max']
        else:
            raise ValueError(f"Axis letter '{axis_letter}' not found in AXIS_UNITS.")
        self.font = font if font else ('Courier New', 10)
        self.unit_label = unit_label

    def show(self):
        unit = f' {self.unit_label}' if self.unit_label else ''
        # Always display as int if value is whole
        display_value = format_display_value(self.current_value)
        layout = [
            [sg.Text(f"Allowed Range: {self.min_val}{unit} to {self.max_val}{unit}", font=self.font, text_color='blue')],
            [sg.Text(f'Current Value{unit}:', font=self.font),
             sg.InputText(str(display_value), key='display', size=(15, 1), font=self.font, justification='center', readonly=False)],
            [sg.Button('7', size=(6, 2), font=self.font),
             sg.Button('8', size=(6, 2), font=self.font),
             sg.Button('9', size=(6, 2), font=self.font)],
            [sg.Button('4', size=(6, 2), font=self.font),
             sg.Button('5', size=(6, 2), font=self.font),
             sg.Button('6', size=(6, 2), font=self.font)],
            [sg.Button('1', size=(6, 2), font=self.font),
             sg.Button('2', size=(6, 2), font=self.font),
             sg.Button('3', size=(6, 2), font=self.font)],
            [sg.Button('-', size=(6, 2), font=self.font),
             sg.Button('0', size=(6, 2), font=self.font),
             sg.Button('.', size=(6, 2), font=self.font)],
            [sg.Button('Clear', size=(6, 2), font=self.font),
             sg.Button('⌫', size=(6, 2), font=self.font)],
            [sg.Button('Cancel', size=(8, 2), font=self.font),
             sg.Button('OK', size=(8, 2), font=self.font)]
        ]
        location = (50, 50)
        popup_window = sg.Window('', layout, modal=True, finalize=True, location=location, keep_on_top=True)
        while True:
            event, values = popup_window.read()
            if event in (sg.WIN_CLOSED, 'Cancel'):
                popup_window.close()
                return None
            elif event == 'OK':
                try:
                    result = round(float(values['display']), 1)
                    # If result is whole, return as int (for display in main GUI)
                    if result.is_integer():
                        result = int(result)
                    if self.min_val <= result <= self.max_val:
                        popup_window.close()
                        return result
                    else:
                        sg.popup_error(f'Value must be between {self.min_val}° and {self.max_val}°', keep_on_top=True, location=(50, 50), font=self.font)
                except ValueError:
                    sg.popup_error('Please enter a valid number (degrees)', keep_on_top=True, location=(50, 50), font=self.font)
            elif event == 'Clear':
                popup_window['display'].update('0')
            elif event == '⌫':
                current = values['display']
                popup_window['display'].update(current[:-1])
            elif event == '-':
                current = values['display']
                # Toggle negative sign: add/remove '-' as needed, but not for zero
                if current and current != '0':
                    if not current.startswith('-'):
                        popup_window['display'].update('-' + current)
                    else:
                        popup_window['display'].update(current[1:])
            elif event == '.':
                current = values['display']
                if '.' not in current:
                    popup_window['display'].update(current + '.')
            elif event in '0123456789':
                current = values['display']
                if '.' in current:
                    frac = current.split('.', 1)[1]
                    if len(frac) >= 1:
                        continue
                popup_window['display'].update(current + event)
