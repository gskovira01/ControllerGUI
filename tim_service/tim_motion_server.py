"""
TIM Motion Server - TCP Socket Listener
========================================

Listens on port 503 for Galil-like ASCII commands from the GUI.
Routes commands to RapidCode (A-D) or ClearCore (E) via the axis router.

Protocol:
    - Command format: "SH A\r\n" (enable axis A)
    - Response format: "0\r\n" or "45.0\r\n" (numeric or status)
    - Timeout: 2 seconds per command
"""

import socket
import threading
import logging
import time
from tim_axis_router import AxisRouter

logger = logging.getLogger(__name__)


class TIMMotionServer:
    """TCP server for motion command dispatch."""
    
    def __init__(self, host='0.0.0.0', port=503, config=None, phantom_mode=False, watchdog=None):
        """
        Initialize motion server.
        
        Args:
            host: Bind address
            port: Bind port
            config: Configuration dict
            phantom_mode: If True, use mock RapidCode (no hardware)
            watchdog: SafetyWatchdog instance
        """
        self.host = host
        self.port = port
        self.config = config or {}
        self.phantom_mode = phantom_mode
        self.watchdog = watchdog
        self.running = False
        self.server_socket = None
        self.client_threads = []
        
        # Initialize axis router (translates commands to RapidCode/ClearCore)
        self.router = AxisRouter(
            config=config,
            phantom_mode=phantom_mode,
            watchdog=watchdog
        )
        logger.info(f"Axis router initialized (phantom_mode={phantom_mode})")
    
    def run(self):
        """Start TCP server and accept connections."""
        self.running = True
        
        # Create server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            logger.info(f"TCP server listening on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to bind socket: {e}")
            raise
        
        # Accept connections
        try:
            while self.running:
                try:
                    self.server_socket.settimeout(1.0)
                    client_socket, client_addr = self.server_socket.accept()
                    logger.info(f"Client connected: {client_addr}")
                    
                    # Handle client in separate thread
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_addr),
                        daemon=True
                    )
                    thread.start()
                    self.client_threads.append(thread)
                
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        
        finally:
            self.shutdown()
    
    def _recv_line(self, client_socket):
        """Read bytes until \\r\\n, returning the stripped line. Returns None on disconnect."""
        buf = b''
        while True:
            chunk = client_socket.recv(256)
            if not chunk:
                return None
            buf += chunk
            if b'\n' in buf:
                line, _, _ = buf.partition(b'\n')
                return line.decode('utf-8', errors='replace').strip()

    def _handle_client(self, client_socket, client_addr):
        """Handle a single client connection."""
        try:
            client_socket.settimeout(5.0)

            while self.running:
                try:
                    # Receive command — read until \r\n so Nagle-coalesced sends
                    # never merge two commands into one dispatch.
                    command = self._recv_line(client_socket)
                    if command is None:
                        break

                    logger.debug(f"[{client_addr}] Received: {command}")
                    
                    # Dispatch to axis router
                    try:
                        response = self.router.dispatch(command)
                        logger.debug(f"[{client_addr}] Response: {response}")
                    except Exception as e:
                        logger.warning(f"Command error: {e}")
                        response = "0"  # Return 0 on error
                    
                    # Send response
                    response_bytes = f"{response}\r\n".encode('utf-8')
                    client_socket.sendall(response_bytes)
                
                except socket.timeout:
                    # Timeout is normal; try next iteration
                    continue
                except Exception as e:
                    logger.warning(f"Client error: {e}")
                    break
        
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        
        finally:
            try:
                client_socket.close()
                logger.info(f"Client disconnected: {client_addr}")
            except Exception:
                pass
    
    def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down motion server...")
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        
        # Close all client connections
        for thread in self.client_threads:
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        
        # Shutdown router
        self.router.shutdown()
        logger.info("Motion server shutdown complete")
