"""Run the installed package's demo while denying non-local network access.

Windows asyncio uses a loopback socket pair internally, so local IPC remains allowed.
"""

import ipaddress
import runpy
import socket
import sys
from pathlib import Path


def local(host):
    if host in {None, "localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def deny_external_network(event, args):
    if event == "socket.connect":
        connection, address = args
        if connection.family in {socket.AF_INET, socket.AF_INET6} and not local(address[0]):
            raise RuntimeError("offline example attempted an external network connection")
    if event in {"socket.getaddrinfo", "socket.gethostbyname"} and not local(args[0]):
        raise RuntimeError("offline example attempted external name resolution")


if __name__ == "__main__":
    sys.addaudithook(deny_external_network)
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "examples/demo.py"), run_name="__main__"
    )
    print("Offline example passed with external network access denied.")
