import subprocess
import os


def run_adb_command(cmd_args):
    try:
        result = subprocess.run(
            cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def connect_device(port):
    if not port:
        return False, "Chưa nhập port."
    cmd = ["adb", "connect", f"localhost:{port}"]
    success, output = run_adb_command(cmd)
    if success and "connected to localhost" in output.lower():
        return True, output
    return False, output


def capture_screenshot(device_name):
    local_path = "screenshot.png"
    cmd_screencap = ["adb", "-s", device_name, "shell",
                     "screencap", "-p", "/sdcard/screenshot.png"]
    cmd_pull = ["adb", "-s", device_name, "pull",
                "/sdcard/screenshot.png", local_path]
    success, out = run_adb_command(cmd_screencap)
    if not success:
        return False, out
    success, out = run_adb_command(cmd_pull)
    if not success:
        return False, out
    return True, local_path


def click_position(device_name, x, y):
    x = int(x)
    y = int(y)
    cmd = ["adb", "-s", device_name, "shell", "input", "tap", str(x), str(y)]
    success, out = run_adb_command(cmd)
    if success:
        return True, f"\u0110\u00e3 click t\u1ea1i ({x}, {y})"
    else:
        return False, out
