"""
TIM RapidCode Adapter - Axes A-D (EtherCAT)
============================================

Translates Galil-like commands into RapidCode API calls for axes A-D.
Handles enable, disable, absolute move, relative move, speed, accel, position query.

This adapter manages the deterministic 1 kHz EtherCAT motion control loop.
"""

import logging
import os
import re
import shutil
import importlib
import time
import importlib.util
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class RapidCodeAdapter:
    """Adapter for RapidCode control of axes A-D (EtherCAT)."""

    def _handle_set_accel(self, axis_idx, value):
        """Stage axis acceleration for next BG motion."""
        try:
            if self._get_axis(axis_idx) is None:
                logger.error(f"Set accel failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            pending = self._ensure_pending_motion(axis_idx)
            pending['accel'] = value
            logger.info(f"Axis {chr(65+axis_idx)} staged accel {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set accel on axis {axis_idx}: {e}")
            return "0"

    def _handle_set_decel(self, axis_idx, value):
        """Stage axis deceleration for next BG motion."""
        try:
            if self._get_axis(axis_idx) is None:
                logger.error(f"Set decel failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            pending = self._ensure_pending_motion(axis_idx)
            pending['decel'] = value
            logger.info(f"Axis {chr(65+axis_idx)} staged decel {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set decel on axis {axis_idx}: {e}")
            return "0"

    def __init__(self, config=None, phantom_mode=False, watchdog=None):
        """
        Initialize RapidCode adapter.
        
        Args:
            config: Configuration dict with RapidCode settings
            phantom_mode: If True, use mock RapidCode (no hardware)
            watchdog: SafetyWatchdog instance
        """
        self.config = config or {}
        self.phantom_mode = phantom_mode
        self.watchdog = watchdog
        self.rmp = None  # RapidCode motionController instance
        self._axis_accessor = None
        self._axes = {}  # Cached axis objects keyed by index
        self.axis_count = 0
        self._unsupported_axes_logged = set()
        self._axis_user_units_mode = {}
        self._axis_units_fallback_logged = set()
        self._pending_motion = {}
        self._motion_start_time = {}
        self.axis_configs = self.config.get('axes', {})
        if not self.axis_configs:
            # yaml has no axes section — fall back to INI (e.g. service started before GUI synced)
            self._load_ini_axis_configs()

        if not phantom_mode:
            self._init_rapidcode()
        else:
            logger.info("RapidCode adapter in PHANTOM MODE (mock)")
            self._init_phantom_rapidcode()

    def _get_mock_axis(self, axis_idx):
        """Return the mock axis object for phantom mode, or None."""
        if not self.phantom_mode or not self.rmp:
            return None
        try:
            return self.rmp.Axis(axis_idx)
        except Exception:
            return None

    def _get_axis(self, axis_idx):
        """Return the cached RapidCode axis object, with extra diagnostics. If cache miss, try to re-cache."""
        if axis_idx < 0 or axis_idx >= self.axis_count:
            axis_letter = chr(65 + axis_idx)
            if axis_letter not in self._unsupported_axes_logged:
                logger.warning("RapidCode axis %s unavailable; controller reports %s configured axes", axis_letter, self.axis_count)
                self._unsupported_axes_logged.add(axis_letter)
            return None
        axis_obj = self._axes.get(axis_idx)
        if axis_obj is None and self.rmp is not None:
            # Defensive: If _axis_accessor is not set, cannot proceed
            if self._axis_accessor is None:
                logger.error("_get_axis: _axis_accessor is None, cannot access axis %s", chr(65 + axis_idx))
                return None
            # Attempt to re-cache the axis object if possible
            axis_method = getattr(self.rmp, self._axis_accessor, None)
            if callable(axis_method):
                try:
                    axis_obj = axis_method(axis_idx)
                    self._axes[axis_idx] = axis_obj
                    logger.info("_get_axis re-cached: idx=%s id=%s type=%s repr=%r", axis_idx, id(axis_obj), type(axis_obj), axis_obj)
                except Exception as cache_err:
                    logger.error("Failed to re-cache axis %s: %s", chr(65 + axis_idx), cache_err)
        if axis_obj is None:
            logger.error("_get_axis cache miss: idx=%s axis_count=%s axes_keys=%s", axis_idx, self.axis_count, list(self._axes.keys()))
        else:
            logger.debug("_get_axis cache hit: idx=%s id=%s type=%s repr=%r", axis_idx, id(axis_obj), type(axis_obj), axis_obj)
        return axis_obj

    def _call_axis_method(self, axis, method_names, *args):
        """Call the first available axis method name and return (result, method_name)."""
        for method_name in method_names:
            method = getattr(axis, method_name, None)
            if callable(method):
                return method(*args), method_name
        # [CHANGE 2026-04-17 17:35:00 -04:00] Include close method-name hints for faster RapidCode API adaptation.
        available = []
        try:
            for name in dir(axis):
                lower = name.lower()
                if any(k in lower for k in ('speed', 'vel', 'accel', 'decel', 'move', 'amp', 'enable', 'position')):
                    available.append(name)
        except Exception:
            pass
        hint = f" Available similar methods: {', '.join(sorted(available)[:30])}" if available else ""
        raise AttributeError(f"Axis method not found. Tried: {', '.join(method_names)}.{hint}")

    def _ensure_pending_motion(self, axis_idx):
        """Create pending motion state for an axis if needed."""
        if axis_idx not in self._pending_motion:
            jerk_default = float(self._get_axis_config(axis_idx).get('jerk', 30.0))
            self._pending_motion[axis_idx] = {
                'mode': None,
                'target': None,
                'distance': None,
                'speed': None,
                'accel': None,
                'decel': None,
                'jerk': jerk_default,
            }
        return self._pending_motion[axis_idx]

    def _get_axis_config(self, axis_idx):
        """Return config dict for axis letter A-D."""
        return self.axis_configs.get(chr(65 + axis_idx), {})

    def _load_ini_axis_configs(self):
        """Load A-D axis parameters from controller_config.ini (single source of truth).

        Overrides any axis values from tim_config.yaml so there is one place to
        edit calibration constants and limits for both the GUI and this service.
        """
        import configparser
        ini_path = Path(__file__).resolve().parent.parent / 'controller_config.ini'
        if not ini_path.exists():
            logger.warning("controller_config.ini not found at %s; axis config falls back to yaml", ini_path)
            return
        cfg = configparser.ConfigParser()
        cfg.read(str(ini_path))
        for axis_letter in ('A', 'B', 'C', 'D'):
            section = f'AXIS_{axis_letter}'
            if section not in cfg:
                logger.warning("[%s] section missing from controller_config.ini", section)
                continue
            s = cfg[section]
            self.axis_configs[axis_letter] = {
                'scaling':            float(s.get('scaling', 1.0)),
                'gearbox':            float(s.get('gearbox', 1.0)),
                'min_pos':            float(s.get('min', 0.0)),
                'max_pos':            float(s.get('max', 360.0)),
                'software_limit_deg': float(s.get('max', 360.0)),
                'jerk':               float(s.get('jerk', 30.0)),
            }
            logger.info(
                "Axis %s config from INI: scaling=%.4f gearbox=%.1f min=%s max=%s jerk=%s",
                axis_letter,
                self.axis_configs[axis_letter]['scaling'],
                self.axis_configs[axis_letter]['gearbox'],
                self.axis_configs[axis_letter]['min_pos'],
                self.axis_configs[axis_letter]['max_pos'],
                self.axis_configs[axis_letter]['jerk'],
            )
        logger.info("Axis A-D parameters loaded from %s", ini_path)

    def _pulse_scale(self, axis_idx):
        """Return GUI pulse-per-user-unit scale for an axis."""
        axis_cfg = self._get_axis_config(axis_idx)
        scaling = float(axis_cfg.get('scaling', 1) or 1)
        gearbox = float(axis_cfg.get('gearbox', 1) or 1)
        return scaling * gearbox

    def _pulses_to_user_units(self, axis_idx, raw_value):
        """Convert GUI pulse value to RapidCode motion units.

        When UserUnitsSet succeeds for an axis, RapidCode units are degrees and we
        convert pulses->degrees. If UserUnitsSet is unavailable/failed, keep native
        controller units by passing pulses through unchanged.
        """
        if self._axis_user_units_mode.get(axis_idx) == 'degrees':
            return float(raw_value) / self._pulse_scale(axis_idx)

        if axis_idx not in self._axis_units_fallback_logged:
            logger.warning(
                "Axis %s using native RapidCode units (UserUnitsSet unavailable); "
                "passing pulse values through without conversion",
                chr(65 + axis_idx),
            )
            self._axis_units_fallback_logged.add(axis_idx)
        return float(raw_value)

    def _user_units_to_pulses(self, axis_idx, user_value):
        """Convert RapidCode motion units back to GUI pulse units."""
        if self._axis_user_units_mode.get(axis_idx) == 'degrees':
            return float(user_value) * self._pulse_scale(axis_idx)
        return float(user_value)

    def _normalize_readback_to_pulses(self, axis_idx, raw_value):
        """Normalize RapidCode readback into GUI pulse units.

        Some RapidCode builds return readback values in user units after UserUnitsSet,
        while others may still return native counts. Use a bounded heuristic to avoid
        4500x inflation when native counts are returned.
        """
        raw = float(raw_value)
        if self._axis_user_units_mode.get(axis_idx) != 'degrees':
            return raw

        scale = self._pulse_scale(axis_idx)
        axis_cfg = self._get_axis_config(axis_idx)
        min_pos = float(axis_cfg.get('min_pos', -360.0))
        max_pos = float(axis_cfg.get('max_pos', 360.0))
        pad = max(180.0, abs(max_pos - min_pos))

        # If raw value is already far beyond expected degree bounds, treat as counts.
        if raw < (min_pos - pad) or raw > (max_pos + pad):
            return raw

        # Treat as user units (degrees) and convert to pulses.
        return raw * scale

    def _log_network_messages(self):
        """Log RapidCode network messages if the API provides them."""
        if self.rmp is None:
            return
        count_get = getattr(self.rmp, 'NetworkLogMessageCountGet', None)
        msg_get = getattr(self.rmp, 'NetworkLogMessageGet', None)
        if not callable(count_get) or not callable(msg_get):
            logger.info("RapidCode network log API not available on this build")
            return
        try:
            msg_count = count_get()
            logger.info("RapidCode network log count: %s", msg_count)
            # Keep output bounded; latest entries are usually most useful.
            start_idx = max(0, int(msg_count) - 20)
            for i in range(start_idx, int(msg_count)):
                try:
                    logger.warning("RapidCode network log[%s]: %s", i, msg_get(i))
                except Exception as msg_err:
                    logger.warning("RapidCode network log[%s] read failed: %s", i, msg_err)
        except Exception as e:
            logger.warning("Failed to query RapidCode network log messages: %s", e)
    
    def _post_network_start_axis_init(self):
        """Query axis count, cache axis objects, apply UserUnitsSet and software limits.

        Must be called after NetworkStart() because AxisCountGet() returns 0 before
        the EtherCAT network is operational.
        """
        axis_count_get = getattr(self.rmp, 'AxisCountGet', None)
        self.axis_count = int(axis_count_get()) if callable(axis_count_get) else 0
        logger.info("RapidCode axis count after NetworkStart: %s", self.axis_count)

        axis_method = None
        if hasattr(self.rmp, 'Axis'):
            axis_method = self.rmp.Axis
            self._axis_accessor = 'Axis'
        elif hasattr(self.rmp, 'AxisGet'):
            axis_method = self.rmp.AxisGet
            self._axis_accessor = 'AxisGet'
        if axis_method:
            for i in range(self.axis_count):
                try:
                    self._axes[i] = axis_method(i)
                    logger.info("Axis %s cached: %s", chr(65 + i), self._axes[i])
                except Exception as cache_err:
                    logger.error("Failed to cache axis %s: %s", chr(65 + i), cache_err)
        else:
            logger.error("RapidCode controller has no Axis/AxisGet accessor")

        for axis_idx in range(self.axis_count):
            axis = self._get_axis(axis_idx)
            if axis is None:
                continue
            pulse_scale = self._pulse_scale(axis_idx)
            if pulse_scale == 1.0:
                self._axis_user_units_mode[axis_idx] = 'native'
                logger.info("Axis %s UserUnitsSet skipped (passthrough mode)", chr(65 + axis_idx))
            else:
                try:
                    self._call_axis_method(axis, ('UserUnitsSet',), pulse_scale)
                    self._axis_user_units_mode[axis_idx] = 'degrees'
                    logger.info("Axis %s UserUnitsSet=%s counts/deg", chr(65 + axis_idx), pulse_scale)
                except Exception as unit_err:
                    self._axis_user_units_mode[axis_idx] = 'native'
                    logger.warning(
                        "Axis %s UserUnitsSet skipped/failed; falling back to native units: %s",
                        chr(65 + axis_idx), unit_err,
                    )

            axis_cfg = self._get_axis_config(axis_idx)
            min_pos = float(axis_cfg.get('min_pos', -360.0))
            max_pos = float(axis_cfg.get('software_limit_deg', axis_cfg.get('max_pos', 360.0)))
            if self._axis_user_units_mode.get(axis_idx) == 'native':
                min_pos = min_pos * pulse_scale if pulse_scale != 1.0 else min_pos
                max_pos = max_pos * pulse_scale if pulse_scale != 1.0 else max_pos
            try:
                lim_high = getattr(axis, 'SoftwareLimitHighSet', None)
                lim_low  = getattr(axis, 'SoftwareLimitLowSet',  None)
                if callable(lim_high) and callable(lim_low):
                    lim_high(max_pos)
                    lim_low(min_pos)
                    logger.info("Axis %s software limits set: low=%s high=%s", chr(65 + axis_idx), min_pos, max_pos)
                else:
                    logger.warning("Axis %s SoftwareLimitHighSet/LowSet not available", chr(65 + axis_idx))
            except Exception as lim_err:
                logger.warning("Axis %s software limit set failed: %s", chr(65 + axis_idx), lim_err)

    def _init_rapidcode(self):
        """Initialize real RapidCode connection."""
        # [CHANGE 2026-04-11 16:20:00 -05:00] Add RSI 11.x and INtime runtime paths in-process
        rsi_path = r'C:\RSI\11.0.3'
        intime_bin_path = r'C:\Program Files (x86)\INtime\bin'
        for extra_path in (rsi_path, intime_bin_path):
            if extra_path not in sys.path:
                sys.path.insert(0, extra_path)
            os.environ['PATH'] = extra_path + os.pathsep + os.environ.get('PATH', '')
        os.environ['RMP_PATH'] = rsi_path

        for dll_path in (rsi_path, intime_bin_path):
            try:
                os.add_dll_directory(dll_path)
            except (AttributeError, FileNotFoundError, OSError):
                pass

        # Try RapidCodePython (RSI 11.x on-disk layout) first, fall back to RSI.RapidCode
        rapidcode_module = None
        motion_controller_cls = None
        creation_parameters_cls = None
        import_errors = []
        for mod_name, cls_name in [
            ('RapidCodePython', 'MotionController'),
            ('RSI.RapidCode',   'MotionController'),
        ]:
            try:
                rapidcode_module = importlib.import_module(mod_name)
                motion_controller_cls = getattr(rapidcode_module, cls_name, None)
                if motion_controller_cls is not None:
                    creation_parameters_cls = getattr(rapidcode_module, 'CreationParameters', None)
                    logger.info(f"RapidCode SDK loaded via '{mod_name}'")
                    break
            except ImportError as exc:
                import_errors.append(f"{mod_name}: {exc}")
                continue

        if motion_controller_cls is None:
            logger.error("RapidCode SDK not found. Install RSI RapidCode 10.7.1+")
            if import_errors:
                logger.error("RapidCode import attempts failed: %s", '; '.join(import_errors))
            raise ImportError("No module named 'RSI'")

        try:
            # [CHANGE 2026-04-17 17:45:00 -04:00] Use RSI sample hardware creation path.
            # Hardware startup should use CreationParameters + MotionController.Create(...),
            # not CreateFromSoftware(), so RmpPath/NodeName are provided explicitly.
            create_controller = getattr(motion_controller_cls, 'Create', None)
            if create_controller is None or creation_parameters_cls is None:
                raise RuntimeError('MotionController.Create or CreationParameters not available')

            creation_params = creation_parameters_cls()
            if hasattr(creation_params, 'RmpPath'):
                creation_params.RmpPath = rsi_path
            if os.name == 'nt' and hasattr(creation_params, 'NodeName'):
                creation_params.NodeName = self.config.get('node_name', 'NodeA')
            if hasattr(creation_params, 'NicPrimary') and self.config.get('ethercat_interface'):
                creation_params.NicPrimary = self.config.get('ethercat_interface')

            logger.info(
                'RapidCode creation parameters: RmpPath=%s, NodeName=%s, NicPrimary=%s',
                getattr(creation_params, 'RmpPath', None),
                getattr(creation_params, 'NodeName', None),
                getattr(creation_params, 'NicPrimary', None),
            )

            original_cwd = os.getcwd()
            try:
                os.chdir(rsi_path)
                self.rmp = create_controller(creation_params)
            finally:
                os.chdir(original_cwd)

            serial_get = getattr(self.rmp, 'SerialNumberGet', None)
            firmware_get = getattr(self.rmp, 'FirmwareVersionGet', None)
            serial = serial_get() if callable(serial_get) else 'unknown'
            firmware = firmware_get() if callable(firmware_get) else 'unknown'
            logger.info("RapidCode connected to real hardware (serial=%s, firmware=%s)", serial, firmware)

            # [CHANGE 2026-04-20] Axis count and caching moved to after NetworkStart.
            # AxisCountGet() returns 0 before the EtherCAT network is up; querying it
            # here caused all axes to be skipped (UserUnitsSet, limits, CSP mode).

            # [CHANGE 2026-04-17 17:10:00 -04:00] Start/diagnose EtherCAT network explicitly at service startup.
            network_state_get = getattr(self.rmp, 'NetworkStateGet', None)
            network_start = getattr(self.rmp, 'NetworkStart', None)
            network_state_before = None
            if callable(network_state_get):
                try:
                    network_state_before = network_state_get()
                    logger.info("RapidCode network state before start: %s", network_state_before)
                except Exception as net_state_err:
                    logger.warning("Could not query network state before start: %s", net_state_err)
            if callable(network_start) and network_state_before != 260:
                startup_dirs = [rsi_path, os.path.dirname(sys.executable)]
                tried = set()
                network_started = False
                for startup_dir in startup_dirs:
                    if not startup_dir or startup_dir in tried:
                        continue
                    tried.add(startup_dir)
                    rta_path = os.path.join(startup_dir, 'RMPnetwork.rta')
                    logger.info(
                        "RapidCode NetworkStart attempt from %s (RMPnetwork.rta exists: %s)",
                        startup_dir,
                        os.path.exists(rta_path),
                    )
                    start_cwd = os.getcwd()
                    try:
                        os.chdir(startup_dir)
                        network_start()
                        logger.info("RapidCode NetworkStart() succeeded from %s", startup_dir)
                        network_started = True
                        self._post_network_start_axis_init()
                        break
                    except Exception as net_start_err:
                        logger.warning("RapidCode NetworkStart() failed from %s: %s", startup_dir, net_start_err)
                        self._log_network_messages()
                    finally:
                        os.chdir(start_cwd)
                if not network_started:
                    # Last-resort fallback: copy RMPnetwork.rta beside python.exe and try once more.
                    rta_src = os.path.join(rsi_path, 'RMPnetwork.rta')
                    rta_dst = os.path.join(os.path.dirname(sys.executable), 'RMPnetwork.rta')
                    try:
                        if os.path.exists(rta_src) and not os.path.exists(rta_dst):
                            shutil.copy2(rta_src, rta_dst)
                            logger.info("Copied RMPnetwork.rta to Python runtime folder: %s", rta_dst)
                            start_cwd = os.getcwd()
                            try:
                                os.chdir(os.path.dirname(sys.executable))
                                network_start()
                                logger.info("RapidCode NetworkStart() succeeded after RMPnetwork.rta copy")
                                network_started = True
                                self._post_network_start_axis_init()
                            finally:
                                os.chdir(start_cwd)
                    except Exception as copy_or_retry_err:
                        logger.warning("RMPnetwork.rta copy/retry fallback failed: %s", copy_or_retry_err)
                        self._log_network_messages()
                if not network_started:
                    logger.error("RapidCode NetworkStart() failed in all startup attempts")
                    self._log_network_messages()
                    last_start_error_get = getattr(self.rmp, 'LastNetworkStartErrorGet', None)
                    if callable(last_start_error_get):
                        try:
                            logger.error('RapidCode LastNetworkStartError=%s', last_start_error_get())
                        except Exception as last_err:
                            logger.warning('Could not read LastNetworkStartError: %s', last_err)
            elif callable(network_start):
                logger.info("RapidCode network already OPERATIONAL; skipping NetworkStart()")
                self._post_network_start_axis_init()
            if callable(network_state_get):
                try:
                    logger.info("RapidCode network state after start: %s", network_state_get())
                except Exception as net_state_err:
                    logger.warning("Could not query network state after start: %s", net_state_err)

            # Set CSP mode AFTER NetworkStart so the SDO write reaches the drive
            # while the network is in OPERATIONAL state (260).
            CSP_MODE = 8  # RSIOperationModeCYCLIC_SYNCHRONOUS_POSITION_MODE
            ACTION_NONE = 0  # RSIActionNONE — do not fault/stop on limit trip
            for axis_idx in range(self.axis_count):
                axis = self._get_axis(axis_idx)
                if axis is None:
                    continue

                # CSP mode
                try:
                    op_mode_set = getattr(axis, 'OperationModeSet', None)
                    if callable(op_mode_set):
                        op_mode_set(CSP_MODE)
                        logger.info("Axis %s OperationModeSet(CSP=8) succeeded", chr(65 + axis_idx))
                    else:
                        logger.warning("Axis %s OperationModeSet not available on this RapidCode build", chr(65 + axis_idx))
                except Exception as mode_err:
                    logger.warning("Axis %s OperationModeSet(CSP) failed: %s", chr(65 + axis_idx), mode_err)

                # Set all limit actions to None so RapidSetup stored values don't
                # interfere with motion. Tries multiple known RSI API method names.
                limit_action_methods = [
                    ('PositionErrorLimitActionSet',  (ACTION_NONE,)),
                    ('ErrorLimitActionSet',           (ACTION_NONE,)),
                    ('HardwarePosLimitActionSet',     (ACTION_NONE,)),
                    ('HardwareNegLimitActionSet',     (ACTION_NONE,)),
                    ('SoftwarePosLimitActionSet',     (ACTION_NONE,)),
                    ('SoftwareNegLimitActionSet',     (ACTION_NONE,)),
                    ('HomeLimitActionSet',            (ACTION_NONE,)),
                ]
                for method_name, args in limit_action_methods:
                    method = getattr(axis, method_name, None)
                    if callable(method):
                        try:
                            method(*args)
                            logger.info("Axis %s %s(NONE) succeeded", chr(65 + axis_idx), method_name)
                        except Exception as lim_err:
                            logger.warning("Axis %s %s failed: %s", chr(65 + axis_idx), method_name, lim_err)

            # Discover and enable EtherCAT slaves
            # TODO: Implement EtherCAT slave discovery

        except Exception as e:
            logger.error(f"Failed to initialize RapidCode: {e}")
            raise
    
    def _init_phantom_rapidcode(self):
        """Initialize mock RapidCode for testing."""
        # Create a mock RapidCode controller
        try:
            from tests.test_mock_rapidcode import MockMotionController
        except Exception:
            # Fallback for environments where "tests" resolves to an external package.
            mock_path = Path(__file__).resolve().parent / 'tests' / 'test_mock_rapidcode.py'
            spec = importlib.util.spec_from_file_location('tim_mock_rapidcode', str(mock_path))
            if spec is None or spec.loader is None:
                raise ImportError(f'Could not load mock module from {mock_path}')
            mock_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mock_module)
            MockMotionController = mock_module.MockMotionController
        self.rmp = MockMotionController()
        logger.info("Mock RapidCode controller initialized")
    
    def handle_command(self, command, axis):
        """
        Handle a Galil-like command for a single axis.
        
        Args:
            command: Full command string (e.g., "PA A=45")
            axis: Single axis letter ('A'-'D')
        
        Returns:
            Response string (numeric value or status)
        """
        if self.rmp is None:
            return "0"
        
        try:
            cmd_upper = command.strip().upper()
            axis_idx = ord(axis) - ord('A')  # A->0, B->1, etc.
            
            # Parse command type and value
            if cmd_upper.startswith('SH'):
                # Enable axis
                return self._handle_enable(axis_idx)
            elif cmd_upper.startswith('MO'):
                # Disable axis
                return self._handle_disable(axis_idx)
            elif cmd_upper.startswith('PA'):
                # Stage absolute position; execute on BG
                value = self._pulses_to_user_units(axis_idx, self._extract_numeric(cmd_upper))
                return self._handle_absolute_move(axis_idx, value)
            elif cmd_upper.startswith('PR'):
                # Stage relative position; execute on BG
                value = self._pulses_to_user_units(axis_idx, self._extract_numeric(cmd_upper))
                return self._handle_relative_move(axis_idx, value)
            elif cmd_upper.startswith('SP'):
                # Set speed
                value = self._pulses_to_user_units(axis_idx, self._extract_numeric(cmd_upper))
                return self._handle_set_speed(axis_idx, value)
            elif cmd_upper.startswith('AC'):
                # Set acceleration
                value = self._pulses_to_user_units(axis_idx, self._extract_numeric(cmd_upper))
                return self._handle_set_accel(axis_idx, value)
            elif cmd_upper.startswith('DC'):
                # Set deceleration
                value = self._pulses_to_user_units(axis_idx, self._extract_numeric(cmd_upper))
                return self._handle_set_decel(axis_idx, value)
            elif cmd_upper.startswith('DP'):
                # Clear position (zero the axis)
                return self._handle_clear_position(axis_idx)
            elif cmd_upper.startswith('CF'):
                # Clear axis faults
                return self._handle_clear_faults(axis_idx)
            elif 'MG _RP' in cmd_upper or 'MG _TP' in cmd_upper:
                # Query actual position
                return self._handle_query_position(axis_idx)
            elif 'MG _MO' in cmd_upper:
                # Query enable/disable status
                return self._handle_query_status(axis_idx)
            elif 'MG _SP' in cmd_upper:
                # Query speed
                return self._handle_query_speed(axis_idx)
            elif 'MG _TC' in cmd_upper:
                # Query torque/current (return 0 for now; real hardware would poll actual current)
                # [CHANGE 2026-04-17 16:45:00 -04:00] Return dummy torque; real path would poll motor current.
                return "0"
            elif 'MG _AC' in cmd_upper:
                # Query acceleration
                # [CHANGE 2026-04-17 16:45:00 -04:00] Return dummy; real path would get axis accel setting.
                return "0"
            elif 'MG _DC' in cmd_upper:
                # Query deceleration
                # [CHANGE 2026-04-17 16:45:00 -04:00] Return dummy; real path would get axis decel setting.
                return "0"
            elif cmd_upper.startswith('BG'):
                # Start motion (compact format like BGA or explicit BG A)
                return self._handle_start_motion(axis_idx)
            elif cmd_upper.startswith('ST'):
                # Stop motion
                return self._handle_stop(axis_idx)
            else:
                logger.warning(f"Unknown RapidCode command: {command}")
                return "0"
        
        except Exception as e:
            logger.error(f"Error handling RapidCode command '{command}': {e}")
            return "0"
    
    def _extract_numeric(self, command):
        """Extract numeric value from command (e.g., '45' from 'PA A=45')."""
        match = re.search(r'=\s*([-+]?\d+\.?\d*)', command)
        if match:
            return float(match.group(1))
        return 0.0
    
    def _handle_disable(self, axis_idx):
        """Disable axis."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                logger.error(f"Disable failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            # [CHANGE 2026-04-17 16:00:00 -04:00] Real hardware path implemented.
            axis.AmpEnableSet(False)
            logger.info(f"Axis {chr(65+axis_idx)} disabled")
            return "0"
        except Exception as e:
            logger.error(f"Failed to disable axis {axis_idx}: {e}")
            return "0"
    
    def _handle_absolute_move(self, axis_idx, value):
        """Stage an absolute position move until BG is received."""
        try:
            if self._get_axis(axis_idx) is None:
                logger.error(f"Absolute move failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            pending = self._ensure_pending_motion(axis_idx)
            pending['mode'] = 'abs'
            pending['target'] = value
            logger.info(f"Axis {chr(65+axis_idx)} staged absolute move to {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_relative_move(self, axis_idx, value):
        """Stage a relative position move until BG is received."""
        try:
            if self._get_axis(axis_idx) is None:
                logger.error(f"Relative move failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            pending = self._ensure_pending_motion(axis_idx)
            pending['mode'] = 'rel'
            pending['distance'] = value
            logger.info(f"Axis {chr(65+axis_idx)} staged relative move by {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to move axis {axis_idx}: {e}")
            return "0"
    
    def _handle_set_speed(self, axis_idx, value):
        """Stage axis speed for next BG motion."""
        try:
            if self._get_axis(axis_idx) is None:
                logger.error(f"Set speed failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            pending = self._ensure_pending_motion(axis_idx)
            pending['speed'] = value
            logger.info(f"Axis {chr(65+axis_idx)} staged speed {value}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to set speed on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_enable(self, axis_idx):
        """Enable axis with extra diagnostics."""
        try:
            axis = self._get_axis(axis_idx)
            logger.info(f"[DEBUG] _handle_enable axis_idx={axis_idx} axis_obj={axis} id={id(axis) if axis else None} type={type(axis) if axis else None}")
            if axis is None:
                logger.error(f"Enable failed: axis object unavailable for {chr(65+axis_idx)} (cache miss)")
                return "0"
            # [CHANGE 2026-04-17 16:00:00 -04:00] Real hardware path implemented.
            try:
                self._call_axis_method(axis, ('Abort', 'Stop'))
            except Exception as stop_err:
                logger.warning(f"Axis {chr(65+axis_idx)} pre-enable stop/abort warning: {stop_err}")

            # ClearFaults can throw transient STOPPING errors if the axis is still settling from Abort/Stop.
            # Treat as recoverable and continue with enable attempts.
            try:
                self._call_axis_method(axis, ('ClearFaults',))
            except Exception as clear_err:
                logger.warning(f"Axis {chr(65+axis_idx)} ClearFaults warning before enable: {clear_err}")

            # RSI samples use AmpEnableSet(True, 750) on hardware.
            try:
                self._call_axis_method(axis, ('AmpEnableSet',), True, 750)
            except Exception as enable_err:
                logger.warning(f"Axis {chr(65+axis_idx)} first enable attempt failed; retrying: {enable_err}")
                try:
                    self._call_axis_method(axis, ('Abort', 'Stop'))
                except Exception:
                    pass
                try:
                    self._call_axis_method(axis, ('ClearFaults',))
                except Exception:
                    pass
                self._call_axis_method(axis, ('AmpEnableSet',), True, 750)

            logger.info(f"Axis {chr(65+axis_idx)} enabled")
            return "1"
        except Exception as e:
            logger.error(f"Failed to enable axis {axis_idx}: {e}", exc_info=True)
            return "0"

    def _handle_clear_faults(self, axis_idx):
        """Clear axis faults without enabling motion."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                logger.error(f"Clear faults failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"

            # Bring the axis out of transient stop states before clearing faults.
            try:
                self._call_axis_method(axis, ('Abort', 'Stop'))
            except Exception as stop_err:
                logger.warning(f"Axis {chr(65+axis_idx)} clear-fault pre-stop warning: {stop_err}")

            self._call_axis_method(axis, ('ClearFaults',))
            logger.info(f"Axis {chr(65+axis_idx)} faults cleared")
            return "1"
        except Exception as e:
            logger.error(f"Failed to clear faults on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_position(self, axis_idx):
        """Query actual position, always return last cached value unless first read."""
        try:
            axis = self._get_axis(axis_idx)
            if not hasattr(self, '_last_position'):
                self._last_position = {}
            if axis is not None:
                position = axis.ActualPositionGet()
                norm_pos = self._normalize_readback_to_pulses(axis_idx, position)
                # Only update cache if nonzero or cache is empty
                if norm_pos != 0 or axis_idx not in self._last_position:
                    self._last_position[axis_idx] = norm_pos
            # Always return last cached value (never zero unless first value is zero)
            return str(self._last_position.get(axis_idx, "0"))
        except Exception as e:
            logger.error(f"Failed to query position on axis {axis_idx}: {e}")
            return str(self._last_position.get(axis_idx, "0"))
    
    def _handle_query_status(self, axis_idx):
        """Query enable/disable status."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                # Axis may be intentionally unavailable (e.g., only A/B configured).
                return "0"
            # [CHANGE 2026-04-17 16:00:00 -04:00] Real hardware path implemented.
            # AmpEnableGet returns True if axis is enabled
            try:
                enabled, _ = self._call_axis_method(axis, ('AmpEnableGet', 'IsEnabled'))
            except AttributeError:
                # Some Axis variants expose state as property/enum; degrade gracefully.
                enabled = False
            return "1" if enabled else "0"
        except Exception as e:
            logger.error(f"Failed to query status on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_query_speed(self, axis_idx):
        """Query current speed."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                # Axis may be intentionally unavailable (e.g., only A/B configured).
                return "0"
            # [CHANGE 2026-04-17 16:00:00 -04:00] Real hardware path implemented.
            speed = axis.ActualVelocityGet()
            return str(self._normalize_readback_to_pulses(axis_idx, speed))
        except Exception as e:
            logger.error(f"Failed to query speed on axis {axis_idx}: {e}")
            return "0"
    
    def _handle_clear_position(self, axis_idx):
        """Zero the position register — software offset approach not yet implemented."""
        logger.info("Axis %s Zero Position requested (not yet implemented)", chr(65 + axis_idx))
        return "1"

    def _handle_stop(self, axis_idx):
        """Stop axis motion."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                logger.error(f"Stop failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"
            # [CHANGE 2026-04-17 16:00:00 -04:00] Real hardware path implemented.
            _, method_used = self._call_axis_method(axis, ('Abort', 'Stop'))
            logger.info(f"Axis {chr(65+axis_idx)} stopped")
            logger.debug(f"Axis {chr(65+axis_idx)} stop method: {method_used}")
            return "1"
        except Exception as e:
            logger.error(f"Failed to stop axis {axis_idx}: {e}")
            return "0"

    def _handle_start_motion(self, axis_idx):
        """Execute staged RapidCode motion on BG."""
        try:
            axis = self._get_axis(axis_idx)
            if axis is None:
                logger.error(f"Start motion failed: axis object unavailable for {chr(65+axis_idx)}")
                return "0"

            # Reject BG if axis is disabled — operator must explicitly enable before moving.
            amp_enable_get = getattr(axis, 'AmpEnableGet', None)
            if callable(amp_enable_get):
                try:
                    if not bool(amp_enable_get()):
                        logger.warning(f"Axis {chr(65+axis_idx)} BG rejected: axis is disabled")
                        return "0"
                except Exception as amp_state_err:
                    logger.warning(f"Axis {chr(65+axis_idx)} AmpEnableGet failed: {amp_state_err}")

            # Ignore duplicate BG while axis is in motion, but time out after 10s to avoid
            # getting stuck when MotionDoneGet never clears (e.g. zero-distance move).
            motion_done_get = getattr(axis, 'MotionDoneGet', None)
            if callable(motion_done_get):
                try:
                    if not bool(motion_done_get()):
                        start_time = self._motion_start_time.get(axis_idx)
                        elapsed = (time.time() - start_time) if start_time else 999
                        if elapsed < 10.0:
                            logger.info(f"Axis {chr(65+axis_idx)} BG ignored; motion already in progress ({elapsed:.1f}s)")
                            return "1"
                        else:
                            logger.warning(f"Axis {chr(65+axis_idx)} MotionDoneGet stuck after {elapsed:.1f}s; forcing new move")
                except Exception:
                    pass

            # Clear residual faults right before issuing a new move.
            try:
                self._call_axis_method(axis, ('ClearFaults',))
            except Exception:
                pass

            pending = self._ensure_pending_motion(axis_idx)
            mode = pending.get('mode')
            if mode == 'abs':
                target = pending.get('target')
                if target is None:
                    return "0"
                speed = pending.get('speed')
                accel = pending.get('accel')
                decel = pending.get('decel')
                jerk = pending.get('jerk') if pending.get('jerk') is not None else float(self._get_axis_config(axis_idx).get('jerk', 30.0))
                try:
                    if None not in (speed, accel, decel):
                        logger.info(f"Axis {chr(65+axis_idx)} MoveSCurve args: target={target}, speed={speed}, accel={accel}, decel={decel}, jerk={jerk}")
                        _, method_used = self._call_axis_method(axis, ('MoveSCurve',), target, speed, accel, decel, jerk)
                    else:
                        logger.warning(f"Axis {chr(65+axis_idx)} MoveSCurve missing speed/accel/decel; falling back to position-only move")
                        _, method_used = self._call_axis_method(axis, ('MoveSCurve', 'MoveAbsolute'), target)
                except TypeError as te:
                    logger.warning(f"Axis {chr(65+axis_idx)} MoveSCurve full-params TypeError ({te}); falling back to position-only")
                    _, method_used = self._call_axis_method(axis, ('MoveSCurve', 'MoveAbsolute'), target)
            elif mode == 'rel':
                distance = pending.get('distance')
                if distance is None:
                    return "0"
                speed = pending.get('speed')
                accel = pending.get('accel')
                decel = pending.get('decel')
                jerk = pending.get('jerk') if pending.get('jerk') is not None else float(self._get_axis_config(axis_idx).get('jerk', 30.0))
                try:
                    if None not in (speed, accel, decel):
                        logger.info(f"Axis {chr(65+axis_idx)} MoveRelative args: distance={distance}, speed={speed}, accel={accel}, decel={decel}, jerk={jerk}")
                        _, method_used = self._call_axis_method(axis, ('MoveRelative',), distance, speed, accel, decel, jerk)
                    else:
                        logger.warning(f"Axis {chr(65+axis_idx)} MoveRelative missing speed/accel/decel; falling back to position-only")
                        current = axis.ActualPositionGet()
                        _, method_used = self._call_axis_method(axis, ('MoveSCurve', 'MoveAbsolute'), current + distance)
                except TypeError as te:
                    logger.warning(f"Axis {chr(65+axis_idx)} MoveRelative full-params TypeError ({te}); falling back to position-only")
                    current = axis.ActualPositionGet()
                    _, method_used = self._call_axis_method(axis, ('MoveSCurve', 'MoveAbsolute'), current + distance)
            else:
                logger.info(f"Axis {chr(65+axis_idx)} BG received with no staged motion")
                return "0"

            self._motion_start_time[axis_idx] = time.time()
            logger.info(f"Axis {chr(65+axis_idx)} motion started via {method_used}")
            # One-shot consume of staged target so repeated BG doesn't re-issue unexpectedly.
            pending['mode'] = None
            pending['target'] = None
            pending['distance'] = None
            return "1"
        except Exception as e:
            logger.error(f"Failed to start axis {axis_idx}: {e}")
            return "0"
    
    def shutdown(self):
        """Graceful shutdown of RapidCode connection."""
        logger.info("Shutting down RapidCode adapter...")
        
        if self.rmp and not self.phantom_mode:
            try:
                # [CHANGE 2026-04-17 16:00:00 -04:00] Disable all real axes on shutdown.
                for i in range(self.axis_count):
                    try:
                        axis = self._get_axis(i)
                        if axis is not None:
                            axis.AmpEnableSet(False)
                    except Exception:
                        pass
                self.rmp = None
                logger.info("RapidCode disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting RapidCode: {e}")
