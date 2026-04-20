"""
TIM Motion Service - Main Entry Point
======================================

The TIM (iPC400) Motion Service is the single authority for all motion control.
It owns RapidCode (axes A-D, EtherCAT) and routes ClearCore (axis E) commands.

The service exposes a TCP socket at port 503 that accepts Galil-like ASCII commands
and translates them into RapidCode or ClearCore calls.

Usage:
    python tim_motion_service.py --config tim_config.yaml
    python tim_motion_service.py --phantom  # For testing without RapidCode

Revision History:
    2026-04-11: Initial scaffold for TIM system design.
"""

import sys
import argparse
import logging
import threading
import time
import yaml
from pathlib import Path
from tim_motion_server import TIMMotionServer
from tim_safety_watchdog import SafetyWatchdog

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('tim_motion_service.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config(config_path):
    """Load YAML configuration file."""
    config_file = Path(config_path)
    if not config_file.is_absolute():
        # [CHANGE 2026-04-11 12:08:00 -04:00] Resolve relative config paths from this script's folder.
        # This keeps startup reliable even when launched outside tim_service/.
        config_file = Path(__file__).resolve().parent / config_file

    if not config_file.exists():
        logger.error(f"Config file not found: {config_file}")
        sys.exit(1)
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"Loaded configuration from {config_file}")
    return config


def _run_status_gui(server, watchdog, host, port, phantom_mode):
    """
    Small tkinter status window for the TIM Motion Service.
    Shows uptime, connection count, phantom mode, and a Stop button.
    Blocks until the window is closed or Stop is clicked.
    """
    # [CHANGE 2026-04-17 16:30:00 -04:00] Status GUI added for operator use on iPC400.
    import tkinter as tk

    start_time = time.time()
    stop_requested = threading.Event()

    root = tk.Tk()
    root.title('TIM Motion Service')
    root.resizable(False, False)
    root.attributes('-topmost', True)

    FONT_TITLE = ('Segoe UI', 14, 'bold')
    FONT_BODY  = ('Segoe UI', 11)
    FONT_STOP  = ('Segoe UI', 12, 'bold')
    GREEN  = '#00CC00'
    RED    = '#FF3333'
    YELLOW = '#FFA500'
    BG     = '#1e1e1e'
    FG     = '#ffffff'

    root.configure(bg=BG)

    tk.Label(root, text='TIM Motion Service', font=FONT_TITLE, bg=BG, fg=FG).pack(pady=(14, 2))

    dot_var  = tk.StringVar(value='●')
    dot_lbl  = tk.Label(root, textvariable=dot_var, font=('Segoe UI', 22), bg=BG, fg=GREEN)
    dot_lbl.pack()

    status_var = tk.StringVar(value='Running')
    tk.Label(root, textvariable=status_var, font=FONT_BODY, bg=BG, fg=GREEN).pack()

    info_var = tk.StringVar()
    tk.Label(root, textvariable=info_var, font=FONT_BODY, bg=BG, fg=FG, justify='left').pack(padx=20, pady=6)

    def on_stop():
        stop_requested.set()
        status_var.set('Stopping…')
        dot_lbl.config(fg=YELLOW)
        stop_btn.config(state='disabled')
        server.running = False  # Signal server loop to exit
        root.after(1200, root.destroy)

    stop_btn = tk.Button(
        root, text='Stop Service', command=on_stop,
        font=FONT_STOP, bg=RED, fg=FG, activebackground='#cc0000',
        relief='flat', padx=16, pady=8, cursor='hand2'
    )
    stop_btn.pack(pady=(4, 16))

    mode_label = 'PHANTOM MODE' if phantom_mode else f'Port {port}'
    tk.Label(root, text=mode_label, font=('Segoe UI', 9), bg=BG, fg='#888888').pack(pady=(0, 8))

    def tick():
        if stop_requested.is_set():
            return
        elapsed = int(time.time() - start_time)
        h, rem = divmod(elapsed, 3600)
        m, s   = divmod(rem, 60)
        uptime  = f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'
        clients = len([t for t in getattr(server, 'client_threads', []) if t.is_alive()])
        info_var.set(f'Uptime:      {uptime}\nClients:     {clients}\nListening:   {host}:{port}')
        root.after(1000, tick)

    tick()
    root.mainloop()


def main():
    """Main entry point for TIM Motion Service."""
    parser = argparse.ArgumentParser(
        description='TIM Motion Service - iPC400 Motion Control Gateway'
    )
    parser.add_argument(
        '--config',
        default='tim_config.yaml',
        help='Path to configuration file (default: tim_config.yaml)'
    )
    parser.add_argument(
        '--phantom',
        action='store_true',
        help='Run in phantom mode (mock RapidCode, no hardware)'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='TCP server bind address (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=503,
        help='TCP server port (default: 503)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--gui',
        action='store_true',
        help='Show a small status window with a Stop button'
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 80)
    logger.info("TIM Motion Service Starting")
    logger.info("=" * 80)
    logger.info(f"Phantom mode: {args.phantom}")
    logger.info(f"Server: {args.host}:{args.port}")
    
    # Load configuration
    config = load_config(args.config)

    # Startup delay — allows INtime and EtherCAT to fully initialize before
    # RapidCode connects. Configured via service.startup_delay_sec in yaml.
    startup_delay = int(config.get('service', {}).get('startup_delay_sec', 0))
    if startup_delay > 0 and not args.phantom:
        logger.info("Waiting %d seconds for INtime/EtherCAT to initialize...", startup_delay)
        time.sleep(startup_delay)
        logger.info("Startup delay complete — initializing RapidCode")

    # Initialize safety watchdog
    watchdog = SafetyWatchdog(config.get('safety', {}))
    logger.info("Safety watchdog initialized")
    
    # Initialize motion server
    try:
        server = TIMMotionServer(
            host=args.host,
            port=args.port,
            config=config,
            phantom_mode=args.phantom,
            watchdog=watchdog
        )
        logger.info(f"TIM Motion Server initialized on {args.host}:{args.port}")
    except Exception as e:
        logger.error(f"Failed to initialize motion server: {e}")
        sys.exit(1)
    
    # Start server (blocks until shutdown)
    try:
        logger.info("Starting motion server...")
        if args.gui:
            # [CHANGE 2026-04-17 16:30:00 -04:00] Optional status window; server runs in background thread.
            server_thread = threading.Thread(target=server.run, daemon=True)
            server_thread.start()
            _run_status_gui(server, watchdog, args.host, args.port, args.phantom)
        else:
            server.run()
    except KeyboardInterrupt:
        logger.info("Shutdown requested (Ctrl+C)")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("Shutting down...")
        server.shutdown()
        watchdog.shutdown()
        logger.info("TIM Motion Service stopped")


if __name__ == '__main__':
    main()
