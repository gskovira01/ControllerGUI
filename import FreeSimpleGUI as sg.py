import FreeSimpleGUI as sg
layout = [[sg.Button('Test')]]
window = sg.Window('Test', layout)
while True:
    event, _ = window.read()
    print('Event:', event)
    if event == sg.WIN_CLOSED:
        break
window.close()