"""Test helper utilities"""

import socket


def get_free_port() -> int:
    """Get a free port for testing"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


# Default test port - different from production default (41794)
TEST_PORT = 41795
