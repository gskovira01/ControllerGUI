"""
Standalone RapidCode hardware probe for the iPC400.

Runs the RSI sample-style controller creation path using CreationParameters,
attempts NetworkStart(), and dumps network/controller diagnostics without
involving the TIM socket service.
"""

import os
import sys
import traceback


# [CHANGE 2026-04-17 17:55:00 -04:00] Minimal RSI-style diagnostic path.
RSI_PATH = r"C:\RSI\11.0.3"
INTIME_BIN = r"C:\Program Files (x86)\INtime\bin"
NODE_NAME = "NodeA"


def _setup_imports():
    if os.path.isdir(INTIME_BIN):
        try:
            os.add_dll_directory(INTIME_BIN)
        except Exception:
            pass

    if RSI_PATH not in sys.path:
        sys.path.insert(0, RSI_PATH)

    import RapidCodePython as RapidCode
    return RapidCode


def _enum_name(rapidcode, prefix, value):
    for name in dir(rapidcode):
        if name.startswith(prefix) and getattr(rapidcode, name) == value:
            return name
    return str(value)


def _print_network_logs(controller):
    count_get = getattr(controller, "NetworkLogMessageCountGet", None)
    msg_get = getattr(controller, "NetworkLogMessageGet", None)
    if not callable(count_get) or not callable(msg_get):
        print("Network log API not available on this RapidCode build")
        return

    try:
        count = int(count_get())
        print(f"Network log count: {count}")
        for idx in range(max(0, count - 20), count):
            try:
                print(f"  [{idx}] {msg_get(idx)}")
            except Exception as err:
                print(f"  [{idx}] <read failed: {err}>")
    except Exception as err:
        print(f"Failed to query network logs: {err}")


def main():
    print("=" * 80)
    print("RSI Network Probe")
    print("=" * 80)
    print(f"RSI_PATH: {RSI_PATH}")
    print(f"Python:   {sys.executable}")
    print(f"CWD:      {os.getcwd()}")

    RapidCode = _setup_imports()
    print(f"RapidCode import OK: {RapidCode.__file__}")

    motion_controller_cls = RapidCode.MotionController
    creation_params_cls = RapidCode.CreationParameters

    creation_params = creation_params_cls()
    if hasattr(creation_params, "RmpPath"):
        creation_params.RmpPath = RSI_PATH
    if hasattr(creation_params, "NodeName"):
        creation_params.NodeName = NODE_NAME

    print(
        "CreationParameters:",
        f"RmpPath={getattr(creation_params, 'RmpPath', None)}",
        f"NodeName={getattr(creation_params, 'NodeName', None)}",
        f"NicPrimary={getattr(creation_params, 'NicPrimary', None)}",
    )

    controller = None
    try:
        original_cwd = os.getcwd()
        try:
            os.chdir(RSI_PATH)
            controller = motion_controller_cls.Create(creation_params)
        finally:
            os.chdir(original_cwd)

        print(f"Version:  {controller.VersionGet()}")
        print(f"Serial:   {controller.SerialNumberGet()}")
        print(f"Axes:     {controller.AxisCountGet()}")

        state_before = controller.NetworkStateGet()
        print(
            "Network state before start:",
            state_before,
            _enum_name(RapidCode, "RSINetworkState_RSINetworkState", state_before),
        )

        try:
            controller.NetworkStart()
            print("NetworkStart(): SUCCESS")
        except Exception as err:
            print(f"NetworkStart(): FAILED -> {err}")

        state_after = controller.NetworkStateGet()
        print(
            "Network state after start:",
            state_after,
            _enum_name(RapidCode, "RSINetworkState_RSINetworkState", state_after),
        )

        last_err_get = getattr(controller, "LastNetworkStartErrorGet", None)
        if callable(last_err_get):
            try:
                last_err = last_err_get()
                print(
                    "LastNetworkStartError:",
                    last_err,
                    _enum_name(RapidCode, "RSINetworkStartError_RSINetworkStartError", last_err),
                )
            except Exception as err:
                print(f"LastNetworkStartErrorGet failed: {err}")

        _print_network_logs(controller)

        node_count_get = getattr(controller, "NetworkNodeCountGet", None)
        if callable(node_count_get):
            try:
                node_count = int(node_count_get())
                print(f"NetworkNodeCount: {node_count}")
            except Exception as err:
                print(f"NetworkNodeCountGet failed: {err}")

    except Exception as err:
        print(f"Probe failed: {err}")
        traceback.print_exc()
        raise
    finally:
        if controller is not None:
            try:
                controller.Delete()
            except Exception:
                pass


if __name__ == "__main__":
    main()