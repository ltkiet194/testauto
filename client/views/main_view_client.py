from controllers.adb_controller import ADBController
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import requests
import json
import os
import threading
import time
from PIL import Image, ImageTk
import cv2
import numpy as np
from io import BytesIO

# Thêm thư mục client vào sys.path để import controllers, models
# Điều này hữu ích nếu main_view_client.py nằm trong thư mục con views/
# và client_app.py nằm ở thư mục client/
import sys
current_file_dir = os.path.dirname(os.path.abspath(__file__))  # views/
client_dir = os.path.dirname(current_file_dir)  # client/
if client_dir not in sys.path:
    sys.path.insert(0, client_dir)


class ADBClientStepExecutorApp(ctk.CTk):
    def __init__(self, server_url="http://localhost:5000"):
        super().__init__()
        self.server_url = server_url
        self.controller = ADBController()

        self.title("ADB Client - Script Executor")
        self.geometry("800x900")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.current_session_id = None
        self.current_action_details = None
        self.available_scripts = []

        self.img_cache_dir = os.path.join(client_dir, "img_cache")
        if not os.path.exists(self.img_cache_dir):
            try:
                os.makedirs(self.img_cache_dir)
            except OSError as e:
                messagebox.showerror(
                    "Error", f"Could not create image cache directory: {self.img_cache_dir}\n{e}")
                self.destroy()  # Không thể tiếp tục nếu không có cache
                return

        self.execution_thread = None
        self.stop_execution_event = threading.Event()

        self._setup_ui()  # Đổi tên để tránh trùng với CTk widget setup
        self._ping_server()  # Ping server khi khởi động
        self.fetch_scripts_from_server()

    def _setup_ui(self):
        # --- Server Connection & Script Selection ---
        top_frame = ctk.CTkFrame(self)
        top_frame.pack(pady=10, padx=10, fill="x")

        ctk.CTkLabel(top_frame, text="Server URL:").pack(side="left", padx=5)
        self.entry_server_url = ctk.CTkEntry(top_frame, width=220)
        self.entry_server_url.insert(0, self.server_url)
        self.entry_server_url.pack(side="left", padx=5)
        ctk.CTkButton(top_frame, text="Ping Server",
                      command=self._ping_server, width=100).pack(side="left", padx=5)

        ctk.CTkLabel(top_frame, text="Scripts:").pack(
            side="left", padx=(10, 0))
        # command=self.on_script_selected bỏ qua
        self.combo_scripts = ctk.CTkOptionMenu(
            top_frame, values=["Loading..."], width=150)
        self.combo_scripts.pack(side="left", padx=5)
        ctk.CTkButton(top_frame, text="Refresh Scripts",
                      command=self.fetch_scripts_from_server, width=120).pack(side="left", padx=5)

        adb_client_frame = ctk.CTkFrame(self)
        adb_client_frame.pack(pady=(0, 10), padx=10, fill="x")
        ctk.CTkLabel(adb_client_frame, text="Client ADB Port:").pack(
            side="left", padx=5)
        self.entry_adb_port = ctk.CTkEntry(
            adb_client_frame, placeholder_text="16480", width=80)
        self.entry_adb_port.insert(0, "16480")
        self.entry_adb_port.pack(side="left", padx=5)
        ctk.CTkButton(adb_client_frame, text="Connect ADB",
                      command=self.connect_adb_client, width=120).pack(side="left", padx=5)
        self.label_adb_client_status = ctk.CTkLabel(
            adb_client_frame, text="ADB: Disconnected")
        self.label_adb_client_status.pack(
            side="left", padx=10, expand=True, fill="x")

        exec_control_frame = ctk.CTkFrame(self)
        exec_control_frame.pack(pady=(0, 5), padx=10, fill="x")
        self.btn_run_script = ctk.CTkButton(
            exec_control_frame, text="▶️ Run Selected Script", command=self.start_script_execution_thread, width=200)
        self.btn_run_script.pack(side="left", padx=5)
        self.btn_stop_script = ctk.CTkButton(exec_control_frame, text="⏹️ Stop Script",
                                             command=self.request_stop_script_execution, state="disabled", fg_color="red", width=120)
        self.btn_stop_script.pack(side="left", padx=5)

        self.label_status = ctk.CTkLabel(
            self, text="Status: Idle", wraplength=780, justify="left", anchor="w")
        self.label_status.pack(pady=5, padx=10, fill="x")

        self.progress_bar_label = ctk.CTkLabel(
            self, text="Image Download Progress:", anchor="w")
        self.progress_bar = ctk.CTkProgressBar(self, width=780)
        self.progress_bar.set(0)

        self.frame_image_client = ctk.CTkFrame(self)
        self.frame_image_client.pack(
            pady=10, padx=10, fill="both", expand=True)
        self.label_image_client = ctk.CTkLabel(
            self.frame_image_client, text="Client Screenshot Preview Area")
        self.label_image_client.pack(expand=True, fill="both")

    def _ping_server(self):
        self.update_status_label("Pinging server...")
        response = self._make_server_request(
            "GET", "/ping", timeout=5)  # Timeout ngắn hơn cho ping
        if response and response.get("message") == "pong":
            self.update_status_label(
                f"Server is responsive. Timestamp: {response.get('timestamp')}")
        elif response:  # Có phản hồi nhưng không phải pong
            self.update_status_label(
                f"Server responded unexpectedly: {response}", is_error=True)
        # Nếu response là None, _make_server_request đã log lỗi rồi

    # Tăng timeout mặc định
    def _make_server_request(self, method, endpoint, json_data=None, stream=False, timeout=20):
        try:
            current_server_url = self.entry_server_url.get().strip('/')
            if not current_server_url:
                self.update_status_label(
                    "Server URL is not set.", is_error=True)
                return None
            url = f"{current_server_url}{endpoint}"

            headers = {}
            if json_data:
                headers['Content-Type'] = 'application/json'

            if method.upper() == 'GET':
                response = requests.get(url, timeout=timeout, stream=stream)
            elif method.upper() == 'POST':
                response = requests.post(
                    url, json=json_data, headers=headers, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()  # Ném lỗi cho 4xx/5xx

            if stream:
                return response

            # Xử lý trường hợp server trả về no content (ví dụ 204)
            if response.status_code == 204 or not response.content:
                return {"success": True, "message": "Request successful with no content."}

            return response.json()

        except requests.exceptions.Timeout:
            error_msg = f"Error: Request to {endpoint} timed out (timeout={timeout}s)."
            self.update_status_label(error_msg, is_error=True)
            return None
        except requests.exceptions.ConnectionError:
            error_msg = f"Error: Could not connect to server at {self.entry_server_url.get().strip('/')} for {endpoint}."
            self.update_status_label(error_msg, is_error=True)
            return None
        except requests.exceptions.HTTPError as e:
            error_msg = f"Error: HTTP error for {endpoint} - {e.response.status_code} {e.response.reason}."
            try:  # Cố gắng đọc nội dung lỗi từ server
                error_details = e.response.json()
                error_msg += f" Server detail: {error_details.get('error', e.response.text)}"
            except json.JSONDecodeError:
                # Giới hạn độ dài
                error_msg += f" Server raw response: {e.response.text[:200]}"
            self.update_status_label(error_msg, is_error=True)
            return None
        except json.JSONDecodeError:
            error_msg = f"Error: Could not decode JSON response from server for {endpoint}."
            self.update_status_label(error_msg, is_error=True)
            return None
        except ValueError as e:  # Lỗi từ client (ví dụ: method không hỗ trợ)
            self.update_status_label(str(e), is_error=True)
            return None
        except Exception as e:  # Bắt các lỗi không lường trước
            error_msg = f"Error: An unexpected error occurred for {endpoint}: {type(e).__name__} - {e}"
            self.update_status_label(error_msg, is_error=True)
            return None

    def update_status_label(self, message, is_error=False):
        def _update():
            timestamp = time.strftime("%H:%M:%S")
            full_message = f"[{timestamp}] {message}"
            self.label_status.configure(text=f"Status: {full_message}",
                                        # Màu đỏ nhạt cho lỗi
                                        text_color=("#FF6B6B" if is_error else "#E0E0E0"))
            print(full_message)
        if hasattr(self, 'after'):  # Đảm bảo widget còn tồn tại
            self.after(0, _update)

    def fetch_scripts_from_server(self):
        self.update_status_label("Fetching scripts from server...")
        data = self._make_server_request("GET", "/api/scripts")
        if data and isinstance(data, list):
            self.available_scripts = data
            if self.available_scripts:
                self.combo_scripts.configure(values=self.available_scripts)
                if self.available_scripts:
                    self.combo_scripts.set(self.available_scripts[0])
                self.update_status_label(
                    f"Scripts loaded: {len(self.available_scripts)}. Select a script and run.")
            else:
                self.combo_scripts.configure(values=["No scripts found"])
                self.combo_scripts.set("No scripts found")
                self.update_status_label("No scripts found on server.")
        elif data and isinstance(data, dict) and "error" in data:
            self.combo_scripts.configure(values=["Error fetching"])
            self.combo_scripts.set("Error fetching")
            self.update_status_label(
                f"Error fetching scripts: {data['error']}", is_error=True)
        else:  # data is None or unexpected format
            self.combo_scripts.configure(values=["Error fetching"])
            self.combo_scripts.set("Error fetching")
            # _make_server_request đã log lỗi rồi, chỉ cần cập nhật UI chung
            if not data:
                self.update_status_label(
                    "Failed to fetch scripts. Check server connection and logs.", is_error=True)

    def connect_adb_client(self):
        port = self.entry_adb_port.get()
        if not port:
            messagebox.showerror(
                "Input Error", "Client ADB Port cannot be empty.")
            return

        self.update_status_label(
            f"Attempting to connect to ADB on port {port}...")
        success, msg = self.controller.connect(port)
        if success:
            status_msg = f"ADB: Connected to {self.controller.get_device_name()}"
            self.label_adb_client_status.configure(text=status_msg)
            self.update_status_label(
                f"Successfully connected to ADB: {self.controller.get_device_name()}")
        else:
            status_msg = "ADB: Connection Failed"
            self.label_adb_client_status.configure(text=status_msg)
            self.update_status_label(
                f"ADB Connection Failed: {msg}", is_error=True)
            messagebox.showerror("ADB Error", msg)

    def start_script_execution_thread(self):
        if not self.controller.get_device_name():
            messagebox.showerror(
                "ADB Error", "Connect to ADB device on client first.")
            return

        selected_script_name = self.combo_scripts.get()
        if not selected_script_name or selected_script_name in ["Loading...", "No scripts found", "Error fetching"]:
            messagebox.showerror(
                "Script Error", "Please select a valid script.")
            return

        if self.execution_thread and self.execution_thread.is_alive():
            messagebox.showwarning(
                "Busy", "A script execution is already in progress.")
            return

        self.stop_execution_event.clear()
        self.btn_run_script.configure(state="disabled")
        self.btn_stop_script.configure(state="normal")

        # Hiển thị progress bar và label của nó
        self.progress_bar_label.pack(
            pady=(5, 0), padx=10, fill="x", before=self.frame_image_client)
        self.progress_bar.pack(pady=(0, 5), padx=10,
                               fill="x", before=self.frame_image_client)
        self.progress_bar.set(0)

        self.execution_thread = threading.Thread(
            target=self._script_execution_worker, args=(selected_script_name,), daemon=True)
        self.execution_thread.start()

    def request_stop_script_execution(self):  # Đổi tên để rõ hơn
        if self.execution_thread and self.execution_thread.is_alive():
            self.update_status_label(
                "Stop requested by user. Attempting to gracefully stop...")
            self.stop_execution_event.set()
            self.btn_stop_script.configure(
                text="Stopping...", state="disabled")  # Cho user biết đang xử lý
        else:
            self.update_status_label("No script running to stop.")
            self._reset_execution_buttons()

    def _reset_execution_buttons(self):
        self.btn_run_script.configure(state="normal")
        self.btn_stop_script.configure(state="disabled", text="⏹️ Stop Script")
        self.progress_bar.pack_forget()
        self.progress_bar_label.pack_forget()

    def _script_execution_worker(self, script_name):
        try:
            self.update_status_label(
                f"Script '{script_name}': Requesting start from server...")
            start_data = self._make_server_request(
                "POST", f"/api/scripts/{script_name}/start")

            if self.stop_execution_event.is_set():  # Kiểm tra nếu user bấm stop ngay lúc này
                self.update_status_label(
                    f"Script '{script_name}' start cancelled by user.", is_error=True)
                return

            if not start_data or "error" in start_data:
                err_msg = start_data.get(
                    'error', 'Unknown server error or no response') if start_data else 'No response from server'
                self.update_status_label(
                    f"Failed to start script '{script_name}': {err_msg}", is_error=True)
                return

            self.current_session_id = start_data.get("session_id")
            self.current_action_details = start_data.get("action")
            required_images = start_data.get("required_images", [])
            initial_message = start_data.get("message", "Script started.")
            self.update_status_label(
                f"'{script_name}': {initial_message} (Session: {self.current_session_id[:8]}...)")

            if not self.current_action_details:  # Server không trả action đầu tiên
                self.update_status_label(
                    f"Script '{script_name}' started but no initial action received. Ending.", is_error=True)
                return

            if required_images:
                self.update_status_label(
                    f"Downloading {len(required_images)} images for '{script_name}'...")
                total_images = len(required_images)
                for i, image_name in enumerate(required_images):
                    if self.stop_execution_event.is_set():
                        self.update_status_label(
                            "Image download cancelled by user.", is_error=True)
                        return

                    self.update_status_label(
                        f"Downloading '{image_name}' ({i+1}/{total_images})...")
                    if not self._ensure_template_image_cached(image_name):
                        self.update_status_label(
                            f"Failed to download/cache '{image_name}'. Stopping script.", is_error=True)
                        messagebox.showerror(
                            "Resource Error", f"Could not obtain image: {image_name}. Script aborted.")
                        return
                    # Update progress bar từ main thread
                    self.after(0, lambda val=(i+1) /
                               total_images: self.progress_bar.set(val))
                self.update_status_label(
                    f"All {total_images} required images are ready for '{script_name}'.")
            else:
                self.update_status_label(
                    f"No specific images required by '{script_name}', or all are cached.")

            self.after(0, lambda: self.progress_bar.set(1))
            time.sleep(0.3)  # Cho user thấy progress bar 100%
            self.after(0, lambda: [self.progress_bar.pack_forget(
            ), self.progress_bar_label.pack_forget()])

            step_count = 1
            while self.current_action_details and not self.stop_execution_event.is_set():
                action = self.current_action_details
                action_type = action.get("type", "Unknown Type")
                image_name = action.get("image")
                action_note = action.get("note", "")  # Lấy note từ script
                status_prefix = f"'{script_name}' [Step {step_count}]"
                self.update_status_label(f"{status_prefix}: Executing '{action_type}' "
                                         f"{f'for image \'{image_name}\'' if image_name else ''} "
                                         f"{f'({action_note})' if action_note else ''}")

                # Action này sẽ tự sleep sau khi hoàn thành
                action_result = self._execute_single_action(action)

                if self.stop_execution_event.is_set():
                    self.update_status_label(
                        f"{status_prefix}: Execution stopped by user during/after action '{action_type}'.")
                    break

                self.update_status_label(
                    f"{status_prefix}: Action '{action_type}' result: {'Success' if action_result.get('success') else 'Failed'}. Notifying server...")
                next_step_data = self._make_server_request("POST", "/api/scripts/action/next",
                                                           json_data={"session_id": self.current_session_id,
                                                                      "result": action_result})

                if self.stop_execution_event.is_set():
                    break

                if not next_step_data or "error" in next_step_data:
                    err_msg = next_step_data.get(
                        'error', 'Unknown server error') if next_step_data else 'No response from server'
                    self.update_status_label(
                        f"{status_prefix}: Error getting next action from server: {err_msg}", is_error=True)
                    break

                self.current_action_details = next_step_data.get("action")
                server_message = next_step_data.get(
                    "message", "Processing next step...")
                self.update_status_label(
                    f"'{script_name}': Server says: \"{server_message}\"")

                if not self.current_action_details:
                    self.update_status_label(
                        f"Script '{script_name}' completed successfully according to server.")
                    messagebox.showinfo("Script Complete",
                                        f"Script '{script_name}' finished.")
                    break
                step_count += 1

        except Exception as e:  # Bắt lỗi không mong muốn trong worker
            self.update_status_label(
                f"Critical error during script '{script_name}' execution: {type(e).__name__} - {e}", is_error=True)
            if self.current_session_id:  # Nếu có session_id, cố gắng thông báo cho server
                messagebox.showerror(
                    "Critical Execution Error", f"Script '{script_name}' encountered a critical error: {e}\nClient will attempt to notify server to stop the session.")
            else:
                messagebox.showerror(
                    "Critical Execution Error", f"Script '{script_name}' encountered a critical error before session start: {e}")

        finally:
            final_status_message = "Script execution worker finished."
            if self.stop_execution_event.is_set():
                final_status_message = f"Script '{script_name}' execution stopped by user."
            elif not self.current_action_details and self.current_session_id:  # Hoàn thành bình thường
                final_status_message = f"Script '{script_name}' finished."

            if self.current_session_id:
                self.update_status_label(
                    f"{final_status_message} Notifying server to end session {self.current_session_id[:8]}...")
                self._make_server_request(
                    "POST", f"/api/scripts/session/{self.current_session_id}/stop")

            self.current_session_id = None
            self.current_action_details = None
            self.after(0, self._reset_execution_buttons)
            self.update_status_label(final_status_message)

    def _execute_single_action(self, action_details):
        action_type = action_details.get("type", "Unknown Type")
        detail_str = action_details.get("details")
        image_name = action_details.get("image")
        delay_after_action_ms = int(action_details.get("delay", 500))

        action_result = {"success": False, "executed_action_type": action_type}
        template_local_path = None

        if image_name:
            template_local_path = os.path.join(self.img_cache_dir, image_name)
            if not os.path.exists(template_local_path):
                action_result["error_message"] = f"FATAL: Image '{image_name}' not found in cache. Pre-download might have failed."
                self.update_status_label(
                    action_result["error_message"], is_error=True)
                # Không sleep ở đây, trả về lỗi ngay để vòng lặp chính xử lý
                return action_result

        if self.stop_execution_event.is_set():
            action_result["error_message"] = "Stopped by user before action execution."
            return action_result

        if action_type == "Click X,Y":
            action_result = self._perform_click_xy(detail_str)
        elif action_type == "Đợi ảnh xuất hiện":
            timeout_ms_for_wait = int(action_details.get("delay", 5000))
            action_result = self._perform_wait_for_image(
                template_local_path, timeout_ms_for_wait / 1000)
            delay_after_action_ms = 200  # Sau khi đợi, delay ngắn hơn trước khi báo server
        elif action_type == "Tìm ảnh và click":
            action_result = self._perform_find_image_and_click(
                template_local_path)
        else:
            action_result[
                "error_message"] = f"Unsupported action type by client: '{action_type}'"
            self.update_status_label(
                action_result["error_message"], is_error=True)

        action_result["executed_action_type"] = action_type

        if not self.stop_execution_event.is_set():
            status_msg_after_action = f"Action '{action_type}' {'succeeded' if action_result.get('success') else 'failed'}. "
            if not action_result.get('success') and "error_message" in action_result:
                status_msg_after_action += f"Error: {action_result['error_message']}. "
            status_msg_after_action += f"Waiting {delay_after_action_ms}ms..."
            self.update_status_label(
                status_msg_after_action, is_error=not action_result.get('success'))

            # Chia nhỏ sleep để có thể dừng nhanh hơn
            sleep_interval = 0.1  # 100ms
            num_intervals = int(delay_after_action_ms /
                                (sleep_interval * 1000))
            for _ in range(num_intervals):
                if self.stop_execution_event.is_set():
                    break
                time.sleep(sleep_interval)
            if not self.stop_execution_event.is_set() and (delay_after_action_ms % (sleep_interval * 1000)) > 0:  # Phần dư
                time.sleep((delay_after_action_ms %
                           (sleep_interval * 1000)) / 1000.0)

        return action_result

    def _ensure_template_image_cached(self, image_name_on_server):
        local_image_path = os.path.join(
            self.img_cache_dir, image_name_on_server)
        if os.path.exists(local_image_path):
            return True

        try:
            response = self._make_server_request(
                # Tăng timeout tải ảnh
                "GET", f"/api/images/{image_name_on_server}", stream=True, timeout=30)
            if not response:
                self.update_status_label(
                    f"Failed to initiate download for '{image_name_on_server}'. Response was None.", is_error=True)
                return False

            with open(local_image_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self.stop_execution_event.is_set():
                        if os.path.exists(local_image_path):
                            try:
                                os.remove(local_image_path)
                            except OSError:
                                pass
                        self.update_status_label(
                            f"Download of '{image_name_on_server}' cancelled.", is_error=True)
                        return False
                    f.write(chunk)
            return True
        except Exception as e:
            self.update_status_label(
                f"Critical error downloading '{image_name_on_server}': {type(e).__name__} - {e}", is_error=True)
            if os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except OSError:
                    pass
            return False

    def _capture_and_display_screenshot(self):
        if self.stop_execution_event.is_set():
            return None  # Dừng sớm
        success, screenshot_path_on_client = self.controller.capture()
        if not success:
            self.update_status_label(
                "Failed to capture screenshot on client.", is_error=True)
            return None

        try:
            img_pil = Image.open(screenshot_path_on_client)

            def _display_on_main_thread():
                if not hasattr(self, 'label_image_client') or not self.label_image_client.winfo_exists():
                    return

                target_w = self.frame_image_client.winfo_width() - 10  # trừ padding
                target_h = self.frame_image_client.winfo_height() - 10

                if target_w <= 1 or target_h <= 1:  # Kích thước không hợp lệ hoặc UI chưa vẽ xong
                    # self.update_status_label("Screenshot preview area not ready for display.", is_error=True)
                    # Không hiển thị nếu không có chỗ
                    return

                resized_img = img_pil.copy()
                resized_img.thumbnail(
                    (target_w, target_h), Image.Resampling.LANCZOS)

                photo = ImageTk.PhotoImage(resized_img)
                self.label_image_client.configure(image=photo, text="")
                self.label_image_client.image = photo  # Giữ reference

            if hasattr(self, 'after'):
                self.after(0, _display_on_main_thread)

            screenshot_cv = cv2.imread(screenshot_path_on_client)
            if screenshot_cv is None:
                self.update_status_label(
                    "Failed to read captured screenshot (OpenCV).", is_error=True)
                return None
            return screenshot_cv
        except FileNotFoundError:
            self.update_status_label(
                f"Screenshot file '{screenshot_path_on_client}' not found after capture.", is_error=True)
            return None
        except Exception as e:
            self.update_status_label(
                f"Error processing/displaying screenshot: {type(e).__name__} - {e}", is_error=True)
            return None

    def _perform_click_xy(self, detail_str):
        result = {"success": False}
        if not detail_str:
            result["error_message"] = "Click X,Y action received no details string."
            self.update_status_label(result["error_message"], is_error=True)
            return result
        try:
            # Cải thiện parsing, cho phép khoảng trắng linh hoạt hơn
            parts = [p.strip() for p in detail_str.split(',')]
            x_str = parts[0].split(':')[1].strip()
            y_str = parts[1].split(':')[1].strip()
            x = int(x_str)
            y = int(y_str)

            if self.stop_execution_event.is_set():
                result["error_message"] = "Stopped by user before click."
                return result

            success_click, msg = self.controller.click(x, y)
            result["success"] = success_click
            if not success_click:
                result["error_message"] = msg or "Click command failed."
                # self.update_status_label(f"Click ({x},{y}) failed: {result['error_message']}", is_error=True) # Đã log ở _execute_single_action
            # else:
                # self.update_status_label(f"Clicked at ({x},{y}).")
            return result
        except Exception as e:
            result[
                "error_message"] = f"Invalid X,Y details string '{detail_str}'. Error: {type(e).__name__} - {e}"
            # self.update_status_label(result["error_message"], is_error=True)
            return result

    def _perform_wait_for_image(self, template_local_path, timeout_seconds, threshold=0.8):
        result = {"success": False}
        if not template_local_path or not os.path.exists(template_local_path):
            result["error_message"] = f"Template image not found locally: {template_local_path}"
            return result

        template_cv = cv2.imread(template_local_path)
        if template_cv is None:
            result["error_message"] = f"Client could not read template: {template_local_path}"
            return result

        start_time = time.time()
        image_basename = os.path.basename(template_local_path)
        # self.update_status_label(f"Waiting for '{image_basename}' (timeout: {timeout_seconds:.1f}s)...")

        while time.time() - start_time < timeout_seconds:
            if self.stop_execution_event.is_set():
                result["error_message"] = "Stopped by user during wait for image."
                return result

            # Hàm này đã tự log lỗi nếu có
            screenshot_cv = self._capture_and_display_screenshot()
            if screenshot_cv is None:
                time.sleep(0.5)  # Chờ chút rồi thử lại nếu chụp lỗi
                continue

            try:
                res = cv2.matchTemplate(
                    screenshot_cv, template_cv, cv2.TM_CCOEFF_NORMED)
                loc = np.where(res >= threshold)
                points = list(zip(*loc[::-1]))  # Chuyển (y,x) thành (x,y)
            # Bắt lỗi nếu kích thước ảnh không khớp (template lớn hơn screenshot)
            except cv2.error as e:
                result["error_message"] = f"OpenCV error matching '{image_basename}': {e}. Template size may be too large for current screen."
                time.sleep(0.5)  # Tránh spam lỗi
                continue  # Thử lại ở lần chụp sau

            if points:
                result["success"] = True
                pt_x, pt_y = int(points[0][0]), int(points[0][1])
                h, w = template_cv.shape[:2]
                result["found_at_raw"] = {"x": pt_x, "y": pt_y}
                result["template_size"] = {"width": w, "height": h}
                result["match_confidence"] = float(
                    np.max(res))  # Thêm độ tin cậy
                # self.update_status_label(f"Found '{image_basename}' at ({pt_x},{pt_y}) with confidence {result['match_confidence']:.2f}.")
                return result

            elapsed_time = int(time.time() - start_time)
            # self.update_status_label(f"Still waiting for '{image_basename}' ({elapsed_time}s / {int(timeout_seconds)}s)")
            time.sleep(0.25)

        # Nếu thoát vòng lặp mà không tìm thấy
        if not self.stop_execution_event.is_set():  # Chỉ ghi là timeout nếu không phải do user dừng
            result["error_message"] = f"Timeout after {timeout_seconds:.1f}s waiting for '{image_basename}'."
        # self.update_status_label(result["error_message"], is_error=True)
        return result

    def _perform_find_image_and_click(self, template_local_path, threshold=0.8):
        result = {"success": False}
        if not template_local_path or not os.path.exists(template_local_path):
            result["error_message"] = f"Template image not found locally: {template_local_path}"
            return result

        template_cv = cv2.imread(template_local_path)
        if template_cv is None:
            result["error_message"] = f"Client could not read template: {template_local_path}"
            return result

        if self.stop_execution_event.is_set():
            result["error_message"] = "Stopped by user before find/click."
            return result

        screenshot_cv = self._capture_and_display_screenshot()
        if screenshot_cv is None:
            result["error_message"] = "Failed to capture screenshot for find and click."
            return result

        image_basename = os.path.basename(template_local_path)
        try:
            res = cv2.matchTemplate(
                screenshot_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(
                res)  # Dùng minMaxLoc để lấy điểm tốt nhất
        except cv2.error as e:
            result["error_message"] = f"OpenCV error matching '{image_basename}': {e}."
            return result

        if max_val >= threshold:
            # max_loc là (x,y) của điểm có giá trị max_val
            pt_x, pt_y = max_loc
            h, w = template_cv.shape[:2]
            center_x = pt_x + w // 2
            center_y = pt_y + h // 2

            result["found_at_raw"] = {"x": int(pt_x), "y": int(pt_y)}
            result["template_size"] = {"width": w, "height": h}
            result["match_confidence"] = float(max_val)
            # self.update_status_label(f"Found '{image_basename}' at ({pt_x},{pt_y}), confidence {max_val:.2f}. Attempting click at ({center_x},{center_y})...")

            if self.stop_execution_event.is_set():
                result["error_message"] = "Stopped by user after finding image, before click."
                result["success"] = False  # Không click được
                return result

            success_click, msg = self.controller.click(center_x, center_y)
            # Chỉ thành công nếu click thành công
            result["success"] = success_click
            if success_click:
                result["clicked_at"] = {"x": center_x, "y": center_y}
                # self.update_status_label(f"Clicked on '{image_basename}' at ({center_x},{center_y}).")
            else:
                result["error_message"] = msg or "Click command failed after finding image."
                # self.update_status_label(result["error_message"], is_error=True)
        else:
            result["success"] = False
            result["error_message"] = f"'{image_basename}' not found on screen (max confidence: {max_val:.2f} < threshold {threshold})."
            # self.update_status_label(result["error_message"], is_error=True)
        return result

    def on_closing(self):
        self.request_stop_script_execution()  # Yêu cầu dừng thread nếu đang chạy

        # Cho thread một chút thời gian để xử lý stop_execution_event
        # và có thể là gửi request cuối cùng lên server
        if self.execution_thread and self.execution_thread.is_alive():
            self.update_status_label(
                "Window closing. Waiting for execution thread to finish...")
            self.execution_thread.join(timeout=3.0)  # Timeout 3 giây
            if self.execution_thread.is_alive():
                self.update_status_label(
                    "Execution thread did not finish in time. Forcing exit.", is_error=True)

        self.destroy()
