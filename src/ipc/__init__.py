"""IPC (Inter-Process Communication) package for socket-based communication between server and UI."""

from .socket_client import (
    SocketClient,
    SocketManager,
    get_socket_manager,
    send_message,
    start_socket_client,
    stop_socket_client,
)
from .socket_client import (
    add_message_handler as add_client_message_handler,
)
from .socket_server import (
    SocketServer,
    add_message_handler,
    broadcast_message,
    get_socket_server,
    start_socket_server,
    stop_socket_server,
)

__all__ = [
    # Server-side exports
    "SocketServer",
    "get_socket_server",
    "start_socket_server",
    "stop_socket_server",
    "broadcast_message",
    "add_message_handler",
    # Client-side exports
    "SocketClient",
    "SocketManager",
    "get_socket_manager",
    "start_socket_client",
    "stop_socket_client",
    "send_message",
    "add_client_message_handler",
]
