from views.main_view_client import ADBClientStepExecutorApp
import sys
import os

# Thêm thư mục client/ vào sys.path
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)


if __name__ == "__main__":
    server_ip = os.environ.get("SCRIPT_SERVER_IP", "localhost")
    server_port = os.environ.get("SCRIPT_SERVER_PORT", "5000")

    app_instance = ADBClientStepExecutorApp(
        server_url=f"http://{server_ip}:{server_port}")
    app_instance.protocol("WM_DELETE_WINDOW", app_instance.on_closing)
    app_instance.mainloop()
