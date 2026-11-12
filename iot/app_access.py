"""
Access key for the Android app.

Requests from the local network (10.x, 172.16-31.x, 192.168.x) need no key, so the
web dashboard keeps working on the farm Wi-Fi. Anything else - including requests
arriving through an internet tunnel, which reach the server from 127.0.0.1 - must
send the key in the X-Farm-Key header. The key is created on first use and kept
in config/.env as APP_KEY; the touchscreen shows it on the Device page.
"""

import hmac
import ipaddress
import secrets
import threading

from farm_ai import read_env, save_env_value

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, easy to type
LOCAL_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7", "fe80::/10")]
FORWARD_HEADERS = ("x-forwarded-for", "forwarded", "x-real-ip", "cf-connecting-ip")

_lock = threading.Lock()


def new_key():
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def app_key():
    """The current key, created and saved the first time it is needed."""
    with _lock:
        key = read_env().get("APP_KEY", "")
        if not key:
            key = new_key()
            save_env_value("APP_KEY", key, header="# Android app access key")
        return key


def reset_key():
    with _lock:
        key = new_key()
        save_env_value("APP_KEY", key, header="# Android app access key")
        return key


def _clean(key):
    return "".join(ch for ch in (key or "").upper() if ch.isalnum())


def key_ok(given):
    return hmac.compare_digest(_clean(given), _clean(app_key()))


def needs_key(client_host, headers):
    """True unless the request comes straight from a device on the local network."""
    if any(h in headers for h in FORWARD_HEADERS):
        return True
    try:
        ip = ipaddress.ip_address(client_host or "")
    except ValueError:
        return True
    return not any(ip in net for net in LOCAL_NETS)
