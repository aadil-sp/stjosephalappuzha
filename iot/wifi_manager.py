"""
Wi-Fi Manager for Raspberry Pi
Scans for wireless networks, reports signal strengths, and manages connections via nmcli.
"""

import subprocess
import shutil
from typing import List, Dict, Any


def is_nmcli_available() -> bool:
    return shutil.which("nmcli") is not None


def get_current_wifi() -> Dict[str, Any]:
    """Returns the currently connected Wi-Fi network and signal strength."""
    if not is_nmcli_available():
        return {"connected": False, "ssid": "Unknown (No nmcli)", "signal": 0}

    try:
        # Run nmcli to get active wifi
        res = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid,signal", "dev", "wifi"],
            capture_output=True,
            text=True,
            timeout=4
        )
        for line in res.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 3 and parts[0].lower() in ["yes", "true"]:
                return {
                    "connected": True,
                    "ssid": parts[1],
                    "signal": int(parts[2]) if parts[2].isdigit() else 100
                }
    except Exception as e:
        print(f"[WiFi] Error reading current wifi: {e}")

    return {"connected": False, "ssid": "Disconnected", "signal": 0}


def scan_wifi_networks() -> List[Dict[str, Any]]:
    """
    Scans for in-range Wi-Fi SSIDs.
    Returns list of dicts: [{"ssid": "MyNet", "signal": 85, "active": True/False, "security": "WPA2"}]
    """
    if not is_nmcli_available():
        return [
            {"ssid": "Asianetgigafiber", "signal": 95, "active": True, "security": "WPA2"},
            {"ssid": "Farm_Extender_2.4G", "signal": 78, "active": False, "security": "WPA2"},
            {"ssid": "Greenhouse_IoT", "signal": 65, "active": False, "security": "WPA2"}
        ]

    try:
        # Rescan and list
        res = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid,signal,security", "dev", "wifi", "list"],
            capture_output=True,
            text=True,
            timeout=8
        )

        networks = []
        seen_ssids = set()

        for line in res.stdout.strip().split("\n"):
            parts = line.split(":")
            if len(parts) >= 3:
                active = parts[0].lower() in ["yes", "true"]
                ssid = parts[1].strip()
                signal = int(parts[2]) if parts[2].isdigit() else 50
                security = parts[3].strip() if len(parts) > 3 else "WPA"

                if ssid and ssid not in seen_ssids:
                    seen_ssids.add(ssid)
                    networks.append({
                        "ssid": ssid,
                        "signal": signal,
                        "active": active,
                        "security": security
                    })

        # Sort: Active first, then by signal descending
        networks.sort(key=lambda x: (not x["active"], -x["signal"]))
        return networks

    except Exception as e:
        print(f"[WiFi] Scan error: {e}")
        return []


def connect_wifi(ssid: str, password: str) -> Dict[str, Any]:
    """Attempts to connect to a Wi-Fi network with provided password."""
    if not is_nmcli_available():
        return {"success": False, "message": "nmcli is not installed."}

    try:
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
        if res.returncode == 0:
            return {"success": True, "message": f"Successfully connected to {ssid}"}
        else:
            return {"success": False, "message": res.stderr.strip() or res.stdout.strip()}

    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Connection attempt timed out."}
    except Exception as e:
        return {"success": False, "message": str(e)}
