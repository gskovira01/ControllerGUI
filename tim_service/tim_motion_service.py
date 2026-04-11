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
    if not Path(config_path).exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info(f"Loaded configuration from {config_path}")
    return config


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
