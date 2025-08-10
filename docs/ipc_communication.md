# IPC Communication System

This document describes the Inter-Process Communication (IPC) system implemented for communication between the Flask server and PySide6 UI.

## Overview

The IPC system uses Unix domain sockets to enable real-time, bidirectional communication between the server and UI processes. This allows for:

- Real-time notifications from server to UI
- UI-initiated actions sent to server
- Status updates and logging
- Event-driven communication

## Architecture

### Components

1. **Socket Server** (`src/ipc/socket_server.py`)

   - Runs as part of the Flask server
   - Accepts connections from UI clients
   - Broadcasts messages to all connected clients
   - Processes incoming messages from UI

2. **Socket Client** (`src/ipc/socket_client.py`)

   - Runs as part of the PySide6 UI
   - Connects to the server socket
   - Sends messages to server
   - Receives and processes messages from server

3. **Socket Manager** (`src/ipc/socket_client.py`)
   - Qt-aware wrapper for the socket client
   - Handles Qt signals and threading
   - Provides easy-to-use interface for UI

### Socket Path

The default socket path is `/tmp/axon-attendance.sock`. This can be customized by passing a different path to the SocketServer/SocketClient constructors.

## Usage

### Server Side

```python
from src.ipc import start_socket_server, broadcast_message, add_message_handler

# Start the socket server
start_socket_server()

# Broadcast a message to all connected UI clients
broadcast_message("Hello from server!")

# Add a message handler to process incoming messages
def handle_ui_message(message: str):
    print(f"Received from UI: {message}")

add_message_handler(handle_ui_message)
```

### UI Side

```python
from src.ipc import start_socket_client, send_message, add_client_message_handler

# Start the socket client
start_socket_client()

# Send a message to the server
payload = {
    "type": "user_message",
    "message": "Hello from UI!",
    "timestamp": None
}
success = send_message(payload)

# Add a message handler to process incoming messages
def handle_server_message(payload: dict):
    print(f"Received from server: {payload}")

add_client_message_handler(handle_server_message)
```

## Integration

### Flask Server Integration

The Flask server automatically starts the socket server when running:

```python
if __name__ == "__main__":
    # Start the socket server for IPC communication
    start_socket_server()

    try:
        app.run(debug=True, host="0.0.0.0", port=1340)
    finally:
        # Cleanup socket server on exit
        stop_socket_server()
```

### PySide6 UI Integration

The UI automatically connects to the socket server:

```python
class BasicApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_socket_communication()

    def setup_socket_communication(self):
        """Setup socket communication with the server."""
        start_socket_client()
        add_client_message_handler(self.handle_server_message)

    def handle_server_message(self, payload: dict):
        """Handle messages received from the server."""
        print(f"Received from server: {payload}")

    def closeEvent(self, event):
        """Handle application close event."""
        stop_socket_client()
        event.accept()
```

## Message Format

Messages are sent as Python dictionaries and automatically converted to JSON strings for transmission:

```python
# Sending structured data
payload = {
    "type": "attendance",
    "personId": "12345",
    "timestamp": "2024-01-01T12:00:00Z"
}
broadcast_message(payload)

# Receiving and parsing
def handle_message(payload: dict):
    if payload["type"] == "attendance":
        # Handle attendance event
        pass
```

## Error Handling

The IPC system includes comprehensive error handling:

- Connection failures are logged
- Disconnected clients are automatically cleaned up
- Thread safety is maintained with locks
- Graceful shutdown on application exit

## Testing

Use the test script to verify IPC communication:

```bash
python test_ipc.py
```

This will start the socket server and send test messages to verify the system is working.

## Troubleshooting

### Common Issues

1. **Socket file already exists**

   - The system automatically removes existing socket files
   - If issues persist, manually remove `/tmp/axon-attendance.sock`

2. **Permission denied**

   - Ensure the application has write permissions to `/tmp`
   - Check file system permissions

3. **Connection refused**
   - Ensure the server is running before starting the UI
   - Check that the socket path matches between server and client

### Debugging

Enable debug logging by setting the log level:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

The IPC system includes detailed logging for troubleshooting connection and message issues.
