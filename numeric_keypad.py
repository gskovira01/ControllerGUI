
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

class NumericKeypad:
    def __init__(self, title, current_value, min_val=0, max_val=54000, font=None):
        self.title = title
        self.current_value = current_value
        self.min_val = min_val
        self.max_val = max_val
        self.font = font if font else ('Courier New', 10)

    def show(self):
        layout = [
            [sg.Text(self.title, font=self.font)],
            [sg.Text(f"Allowed Range: {self.min_val} to {self.max_val}", font=self.font, text_color='blue')],
            [sg.Text('Current Value:', font=self.font),
             sg.InputText(str(self.current_value), key='display', size=(15, 1), font=self.font, justification='center', readonly=False)],
            [sg.Button('7', size=(6, 2), font=self.font),
             sg.Button('8', size=(6, 2), font=self.font),
             sg.Button('9', size=(6, 2), font=self.font)],
            [sg.Button('4', size=(6, 2), font=self.font),
             sg.Button('5', size=(6, 2), font=self.font),
             sg.Button('6', size=(6, 2), font=self.font)],
            [sg.Button('1', size=(6, 2), font=self.font),
             sg.Button('2', size=(6, 2), font=self.font),
             sg.Button('3', size=(6, 2), font=self.font)],
            [sg.Button('Clear', size=(6, 2), font=self.font),
             sg.Button('0', size=(6, 2), font=self.font),
             sg.Button('⌫', size=(6, 2), font=self.font)],
            [sg.Button('Cancel', size=(8, 2), font=self.font),
             sg.Button('OK', size=(8, 2), font=self.font)]
        ]
        location = (50, 50)
        popup_window = sg.Window(self.title, layout, modal=True, finalize=True, location=location, keep_on_top=True)
        while True:
            event, values = popup_window.read()
            if event in (sg.WIN_CLOSED, 'Cancel'):
                popup_window.close()
                return None
            elif event == 'OK':
                try:
                    result = int(values['display'])
                    if self.min_val <= result <= self.max_val:
                        popup_window.close()
                        return result
                    else:
                        sg.popup_error(f'Value must be between {self.min_val} and {self.max_val}', keep_on_top=True, location=(50, 50), font=self.font)
                except ValueError:
                    sg.popup_error('Please enter a valid number', keep_on_top=True, location=(50, 50), font=self.font)
            elif event == 'Clear':
                popup_window['display'].update('0')
            elif event == '⌫':
                current = values['display']
                popup_window['display'].update(current[:-1])
            elif event in '0123456789':
                current = values['display']
                popup_window['display'].update(current + event)
