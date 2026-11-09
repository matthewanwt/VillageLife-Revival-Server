"""Host-port preflight. Legacy client uses port 80 unless separately re-patched.

Never auto-switch the running player to another port: an unmodified client would
continue contacting port 80 and show 'Connection Lost'.
"""
from __future__ import annotations
import socket
from runtime_errors import VillageRuntimeError


def port_available(port: int, host="127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        try:
            server.bind((host, port))
            return True
        except OSError:
            return False


def suggested_ports(count=4):
    """Informational only; do not assume the client can speak to these ports."""
    result = []
    for port in range(8765, 8900):
        if port_available(port):
            result.append(port)
        if len(result) == count:
            break
    return result


def require_client_port(port=80):
    if not port_available(port):
        raise VillageRuntimeError(
            "VL-PORT-IN-USE", f"The game's required localhost port {port} is unavailable.",
            "Close any other local web server using that port and retry. A free alternative port cannot work until the APK's endpoint is rebuilt and verified.",
            details="On Windows use: netstat -ano | findstr :80. Candidate unused ports (not currently usable by the APK): " + ", ".join(map(str, suggested_ports())),
        )
