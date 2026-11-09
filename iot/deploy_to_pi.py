#!/usr/bin/env python3
"""
Deploy local iot/ files to Raspberry Pi via SFTP and restart service.
"""
import os
import sys
import time
import paramiko

def load_env(path):
    """Minimal KEY=VALUE loader for config/.env (git-ignored)."""
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

_ENV = load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", ".env"))

PI_HOST = os.environ.get("PI_HOST", _ENV.get("PI_HOST", "10.180.5.188"))
PI_USER = os.environ.get("PI_USER", _ENV.get("PI_USER", "school"))
PI_PASS = os.environ.get("PI_PASSWORD", _ENV.get("PI_PASSWORD")) or None  # None -> use SSH key
REMOTE_DIR = "/home/school/stjoseph_iot"

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules"}
EXCLUDE_FILES = {".DS_Store"}

def deploy():
    print(f"Connecting to {PI_USER}@{PI_HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(PI_HOST, username=PI_USER, password=PI_PASS, timeout=10)

    sftp = client.open_sftp()

    def ensure_remote_dir(remote_path):
        parts = remote_path.strip("/").split("/")
        cur = ""
        for p in parts:
            cur += "/" + p
            try:
                sftp.stat(cur)
            except IOError:
                try:
                    sftp.mkdir(cur)
                except Exception:
                    pass

    ensure_remote_dir(REMOTE_DIR)

    local_root = os.path.dirname(os.path.abspath(__file__))
    uploaded = 0

    for root, dirs, files in os.walk(local_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_FILES or f.endswith(".pyc"):
                continue
            local_path = os.path.join(root, f)
            rel_path = os.path.relpath(local_path, local_root)
            remote_path = os.path.join(REMOTE_DIR, rel_path).replace("\\", "/")

            ensure_remote_dir(os.path.dirname(remote_path))
            print(f"Uploading {rel_path} -> {remote_path}")
            sftp.put(local_path, remote_path)
            uploaded += 1

    sftp.close()
    print(f"Uploaded {uploaded} files successfully.")

    print("Restarting iot-dashboard service on Pi...")
    if PI_PASS:
        stdin, stdout, stderr = client.exec_command("sudo -S -p '' systemctl restart iot-dashboard")
        stdin.write(PI_PASS + "\n")
        stdin.flush()
    else:
        stdin, stdout, stderr = client.exec_command("sudo -n systemctl restart iot-dashboard")
    err = stderr.read().decode()
    out = stdout.read().decode()
    if err and "password" not in err.lower():
        print("Service restart error:", err)

    time.sleep(2)
    stdin, stdout, stderr = client.exec_command("systemctl is-active iot-dashboard")
    status = stdout.read().decode().strip()
    print(f"iot-dashboard status: {status}")

    # Test api
    stdin, stdout, stderr = client.exec_command("curl -s http://127.0.0.1:8000/api/telemetry")
    telemetry = stdout.read().decode()
    print("Telemetry from Pi:")
    print(telemetry)

    client.close()

if __name__ == "__main__":
    deploy()
