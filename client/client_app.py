from views.main_view_client import ADBClientStepExecutorApp
import sys
import os

# Thêm thư mục client/ vào sys.path để Python có thể tìm thấy các module views, controllers, models
# Giả sử client_app.py nằm trực tiếp trong thư mục client/
CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CLIENT_DIR not in sys.path:
    sys.path.insert(0, CLIENT_DIR)

# Import class App chính từ views

if __name__ == "__main__":
    # Lấy địa chỉ IP của server từ biến môi trường nếu có, mặc định là localhost
    server_ip = os.environ.get("SCRIPT_SERVER_IP", "localhost")
    server_port = os.environ.get("SCRIPT_SERVER_PORT", "5000")

    app_instance = ADBClientStepExecutorApp(
        server_url=f"http://{server_ip}:{server_port}")

    # Xử lý sự kiện đóng cửa sổ một cách an toàn
    app_instance.protocol("WM_DELETE_WINDOW", app_instance.on_closing)

    app_instance.mainloop()
