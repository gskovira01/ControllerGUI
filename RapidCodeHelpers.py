##! @file RapidCodeHelpers.py
##@addtogroup rapidcode-api-samples-py-helpers
##@{
##@brief Helper Functions for checking logged creation errors, starting the network, etc.
##
##
##@n
##@anchor Helper-Functions-PY
##📜 [Helper Functions Python](#Helper-Functions-PY)
##@snippet RapidCodeHelpers.py HelperFunctionsPY
##Learn more in @ref settling. 
##
##@n
## @}
#

##@[HelperFunctionsPY]
import os
import platform
from pathlib import Path
import sys

# Configuration constants
# These constants are used to configure the creation of the motion controller.
# They are intended to be modified by the user to match their specific setup.
RMP_PATH = "" # The path to the RapidCode install directory. If left empty, the script will attempt to find it automatically.

# Windows
NODE_NAME = "" # The INtime node name (default is NodeA)

# Linux
NIC_PRIMARY = "" # The primary NIC to use for EtherCAT communication
CPU_AFFINITY = 0 # The CPU core to use for the RMP firmware

def find_rapid_code_directory(start_directory=None):
  """
  Attempts to find the install directory of RapidCode.
  """
  start_directory = start_directory or os.path.dirname(os.path.abspath(__file__))
  start_path = Path(start_directory)
  
  search_paths = [
    start_path,
    start_path.parent.parent.absolute(),
    start_path.parent.parent.parent.absolute() / "Release",
    Path("/rsi")
  ]

  file_name = "RapidCodePython.py"
  
  for path in search_paths:
    if path.is_dir() and file_name in os.listdir(path):
      return str(path)
  
  raise FileNotFoundError(
    "Could not find RapidCode Directory. "
    "Try entering the path manually, likely C:/RSI/X.X.X"
  )

if platform.system() == "Windows":
    os.add_dll_directory("c:\\Program Files (x86)\\INtime\\bin") #ntx.dll

if RMP_PATH == "":
  rapidcode_dir = find_rapid_code_directory()
else:
  rapidcode_dir = RMP_PATH

sys.path.append(rapidcode_dir)
import RapidCodePython as RapidCode

def get_creation_parameters():
  """
  Create a motion controller and return it. If any errors are found, raise an exception with the error log as the message.
  """
  creation_params:RapidCode.CreationParameters = RapidCode.CreationParameters()
  creation_params.RmpPath = rapidcode_dir
  creation_params.NicPrimary = NIC_PRIMARY

  if platform.system() == "Windows":
    creation_params.NodeName = NODE_NAME
  elif platform.system() == "Linux":
    creation_params.CpuAffinity = CPU_AFFINITY
  else:
    raise Exception("Unsupported platform")

  return creation_params

def check_errors(rsi_object):
    """
    Check for errors in the given rsi_object and print any errors that are found. If the error log contains any errors (not just warnings), raises an exception with the error log as the message.
    Returns a tuple containing a boolean indicating whether the error log contained any errors and the error log string.
    """
    error_string_builder = ""
    i = rsi_object.ErrorLogCountGet()
    while rsi_object.ErrorLogCountGet() > 0:
        error:RapidCode.RsiError = rsi_object.ErrorLogGet()
        error_type = "WARNING" if error.isWarning else "ERROR"
        error_string_builder += f"{error_type}: {error.text}\n"
        if len(error_string_builder) > 0:
            print(error_string_builder)
        if "ERROR" in error_string_builder:
            raise Exception(error_string_builder)
    return "ERROR" in error_string_builder, error_string_builder

def start_the_network(controller):
  """
  Attempts to start the network using the given MotionController object. If the network fails to start, it reads and prints any log messages that may be helpful in determining the cause of the problem, and then raises an RsiError exception.
  """
  if controller.NetworkStateGet() != RapidCode.RSINetworkState_RSINetworkStateOPERATIONAL: # Check if network is started already.
    print("Starting Network..")
    controller.NetworkStart()                                                     # If not. Initialize The Network. (This can also be done from RapidSetup Tool)

  if controller.NetworkStateGet() != RapidCode.RSINetworkState_RSINetworkStateOPERATIONAL: # Check if network is started again.
    messages_to_read = controller.NetworkLogMessageCountGet()                  # Some kind of error starting the network, read the network log messages

    for i in range(messages_to_read):
      print(controller.NetworkLogMessageGet(i))                                 # Print all the messages to help figure out the problem
    print("Expected OPERATIONAL state but the network did not get there.")
    #  raise Exception(Expected OPERATIONAL state but the network did not get there.)# Uncomment if you want your application to exit when the network isn't operational. (Comment when using phantom axis)
  else:                                                                              # Else, of network is operational.
    print("Network Started")
  
##@[HelperFunctionsPY]
