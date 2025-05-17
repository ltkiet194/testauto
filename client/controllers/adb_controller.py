from models import adb_model


class ADBController:
    def __init__(self):
        self.device_name = None

    def connect(self, port):
        success, msg = adb_model.connect_device(port)
        if success:
            self.device_name = f"localhost:{port}"
        return success, msg

    def capture(self):
        if not self.device_name:
            return False, "Chưa kết nối thiết bị."
        return adb_model.capture_screenshot(self.device_name)

    def click(self, x, y):
        if not self.device_name:
            return False, "Chưa kết nối thiết bị."
        return adb_model.click_position(self.device_name, x, y)

    def get_device_name(self):
        return self.device_name
