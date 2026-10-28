"""Proxy policy shared by outbound tool transports."""

import ipaddress
from urllib.parse import urlsplit


def should_trust_environment_proxy(endpoint: str) -> bool:
    """Use configured proxies for remote hosts, but connect to loopback directly."""
    hostname = urlsplit(endpoint).hostname
    if not hostname:
        return True
    if hostname.lower() == "localhost":
        return False
    try:
        return not ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return True
