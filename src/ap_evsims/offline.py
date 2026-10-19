"""Process-local network prohibition for synchronous historical research commands."""
from contextlib import contextmanager
import socket
from unittest.mock import patch

@contextmanager
def offline_mode():
    def denied(*args,**kwargs):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
    original=socket.socket
    class OfflineSocket(original):
        connect=denied
        connect_ex=denied
        sendto=denied
    with patch('socket.socket',OfflineSocket),patch('socket.create_connection',denied),patch('socket.getaddrinfo',denied):
        yield
