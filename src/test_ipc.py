#!/usr/bin/env python3
"""
Test script to verify IPC communication between server and UI.
"""

import time

from src.ipc import broadcast_message, start_socket_server, stop_socket_server


def test_server():
    """Test the socket server functionality."""
    print("Starting socket server...")
    start_socket_server()

    try:
        # Wait a moment for server to start
        time.sleep(1)

        # Send some test messages
        test_messages = [
            {"type": "test", "message": "Hello from server!"},
            {"type": "test", "message": "Test message 1"},
            {"type": "test", "message": "Test message 2"},
            {"type": "test", "data": "JSON message"},
        ]

        for i, payload in enumerate(test_messages):
            print(f"Sending message {i + 1}: {payload}")
            broadcast_message(payload)
            time.sleep(2)

        print("Test completed successfully!")

    finally:
        print("Stopping socket server...")
        stop_socket_server()


if __name__ == "__main__":
    test_server()
