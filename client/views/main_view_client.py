# client/views/main_view_client.py
from controllers.adb_controller import ADBController
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import requests
import json
import os
import threading
import time
# from PIL import Image, ImageTk # Không cần Pillow và ImageTk nữa nếu không show ảnh
import cv2                   # Vẫn cần OpenCV
import numpy as np           # Vẫn cần NumPy
from io import BytesIO

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

        self.title("ADB Client - Script Executor (No Preview)")  # Đổi title
        # Có thể giảm chiều cao nếu không có preview ảnh
        self.geometry("800x500")
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
                    "Fatal Error", f"Could not create image cache directory: {self.img_cache_dir}\n{e}")
                self.destroy()
                return

        self.execution_thread = None
        self.stop_execution_event = threading.Event()

        self._setup_ui()
        self._ping_server()
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
            adb_client_frame, placeholder_text="16448", width=80)
        self.entry_adb_port.insert(0, "16448")
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
        self.btn_stop_script = ctk.CTkButton(exec_control_frame, text="⏹️ Stop Script", command=self.request_stop_script_execution,
                                             state="disabled", fg_color="red", hover_color="#C44242", width=120)
        self.btn_stop_script.pack(side="left", padx=5)

        self.label_status = ctk.CTkLabel(self, text="Status: Idle", wraplength=780,
                                         justify="left", anchor="w", height=100)  # Tăng chiều cao cho status log
        self.label_status.pack(pady=5, padx=10, fill="x")

        self.progress_bar_label = ctk.CTkLabel(
            self, text="Image Download Progress:", anchor="w")
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)

        # Khu vực này giờ có thể không dùng để hiển thị ảnh nữa, hoặc dùng cho mục đích khác
        self.frame_image_placeholder = ctk.CTkFrame(
            self, fg_color="transparent", height=150)  # Giảm chiều cao mặc định
        self.frame_image_placeholder.pack(
            pady=10, padx=10, fill="x", expand=False)  # Không expand nữa
        self.label_info_area = ctk.CTkLabel(
            self.frame_image_placeholder, text="Execution Log Area / Info Placeholder")
        self.label_info_area.pack(expand=True, fill="both")

    def _ping_server(self):
        # ... (Giữ nguyên) ...
        self.update_status_label("Pinging server...")
        current_server_url_for_ping = self.entry_server_url.get().strip('/')
        if not current_server_url_for_ping:
            self.update_status_label(
                "Server URL is empty. Cannot ping.", is_error=True)
            return

        def do_ping():
            response = self._make_server_request(
                "GET", "/api/runtime/ping", timeout=5, server_url_override=current_server_url_for_ping)
            if response and response.get("message") == "pong_runtime":
                self.update_status_label(
                    f"Server is responsive. Timestamp: {response.get('timestamp')}")
            elif response and "error" in response:  # Lỗi từ _make_server_request
                self.update_status_label(
                    f"Ping failed: {response['error']}", is_error=True)
            elif response:
                self.update_status_label(
                    f"Server responded unexpectedly to ping: {str(response)[:200]}", is_error=True)
            else:  # response is None
                self.update_status_label(
                    "Ping failed: No response from server.", is_error=True)

        threading.Thread(target=do_ping, daemon=True).start()

    def _make_server_request(self, method, endpoint, json_data=None, stream=False, timeout=20, server_url_override=None):
        # ... (Giữ nguyên như phiên bản trước, đã xử lý lỗi tốt) ...
        try:
            current_server_url = server_url_override if server_url_override else self.entry_server_url.get().strip('/')
            if not current_server_url:
                print("Error: Server URL is not set in _make_server_request.")
                return {"error": "Client Error: Server URL not set.", "is_client_error": True}
            url = f"{current_server_url}{endpoint}"

            headers = {}
            if json_data:
                headers['Content-Type'] = 'application/json'

            response = None
            if method.upper() == 'GET':
                response = requests.get(url, timeout=timeout, stream=stream)
            elif method.upper() == 'POST':
                response = requests.post(
                    url, json=json_data, headers=headers, timeout=timeout)
            else:
                print(f"CRITICAL: Unsupported HTTP method: {method}")
                return {"error": f"Client internal error: Unsupported HTTP method {method}", "is_client_error": True}

            response.raise_for_status()
            if stream:
                return response
            if response.status_code == 204 or not response.content:
                return {"success": True, "message": f"Request to {endpoint} successful (204 No Content)."}
            return response.json()
        except requests.exceptions.Timeout:
            return {"error": f"Request to {endpoint} timed out (timeout={timeout}s).", "is_network_error": True}
        except requests.exceptions.ConnectionError:
            return {"error": f"Could not connect to server at {current_server_url} for {endpoint}.", "is_network_error": True}
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error for {endpoint} - {e.response.status_code} {e.response.reason}."
            try:
                error_details = e.response.json()
                error_msg += f" Server: {error_details.get('error', e.response.text if e.response.text else 'No details')}"
            except json.JSONDecodeError:
                error_msg += f" Server raw: {e.response.text[:200]}"
            return {"error": error_msg, "status_code": e.response.status_code}
        except json.JSONDecodeError:
            return {"error": f"Could not decode JSON response from server for {endpoint}.", "is_server_error": True}
        except Exception as e:
            return {"error": f"Unexpected error during request to {endpoint}: {type(e).__name__} - {e}", "is_client_error": True}

    def update_status_label(self, message, is_error=False):
        # ... (Giữ nguyên) ...
        def _update_ui_status():
            if not hasattr(self, 'label_status') or not self.label_status.winfo_exists():
                print(
                    f"DEBUG: label_status widget no longer exists. Message: {message}")
                return
            timestamp = time.strftime("%H:%M:%S")
            full_message = f"[{timestamp}] {message}"
            error_color = ("#FF6B6B", "#C44242")
            normal_color = ("gray10", "gray90")
            current_mode = ctk.get_appearance_mode()
            text_color_to_set = error_color[1 if current_mode == "Dark" else 0] if is_error else \
                normal_color[1 if current_mode == "Dark" else 0]
            self.label_status.configure(
                text=f"Status: {full_message}", text_color=text_color_to_set)
            print(full_message)  # Vẫn print ra console để debug dễ hơn
        if hasattr(self, 'after'):
            self.after(0, _update_ui_status)
        else:
            print(f"Fallback print (UI not ready/destroyed): {message}")

    def fetch_scripts_from_server(self):
        # ... (Giữ nguyên) ...
        self.update_status_label("Fetching scripts from server...")

        def do_fetch():
            data = self._make_server_request("GET", "/api/runtime/scripts")

            def update_ui_after_fetch():
                if data and isinstance(data, list):
                    self.available_scripts = data
                    if self.available_scripts:
                        self.combo_scripts.configure(
                            values=self.available_scripts)
                        if self.available_scripts:
                            self.combo_scripts.set(self.available_scripts[0])
                        self.update_status_label(
                            f"Scripts loaded: {len(self.available_scripts)}. Select a script and run.")
                    else:
                        self.combo_scripts.configure(
                            values=["No scripts found"])
                        self.combo_scripts.set("No scripts found")
                        self.update_status_label("No scripts found on server.")
                # Lỗi từ _make_server_request
                elif data and isinstance(data, dict) and "error" in data:
                    self.combo_scripts.configure(values=["Error fetching"])
                    self.combo_scripts.set("Error fetching")
                    self.update_status_label(
                        f"Error fetching scripts: {data['error']}", is_error=True)
                else:
                    self.combo_scripts.configure(values=["Error fetching"])
                    self.combo_scripts.set("Error fetching")
                    if not data:
                        self.update_status_label(
                            "Failed to fetch scripts. Check server connection and logs.", is_error=True)
            if hasattr(self, 'after'):
                self.after(0, update_ui_after_fetch)
        threading.Thread(target=do_fetch, daemon=True).start()

    def connect_adb_client(self):
        # ... (Giữ nguyên) ...
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

    def start_script_execution_thread(self):
        # ... (Giữ nguyên) ...
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
        self.btn_stop_script.configure(state="normal", text="⏹️ Stop Script")

        def _show_progress_bar_setup():
            if not hasattr(self, 'progress_bar_label') or not self.progress_bar_label.winfo_exists():
                return
            # Đổi frame_image_client thành frame_image_placeholder
            self.progress_bar_label.pack(
                pady=(5, 0), padx=10, fill="x", before=self.frame_image_placeholder)
            self.progress_bar.pack(
                pady=(0, 5), padx=10, fill="x", before=self.frame_image_placeholder)
            self.progress_bar.set(0)
        if hasattr(self, 'after'):
            self.after(0, _show_progress_bar_setup)
        self.execution_thread = threading.Thread(
            target=self._script_execution_worker, args=(selected_script_name,), daemon=True)
        self.execution_thread.start()

    def request_stop_script_execution(self):
        # ... (Giữ nguyên) ...
        if self.execution_thread and self.execution_thread.is_alive():
            self.update_status_label(
                "Stop request sent by user. Attempting to gracefully stop current action...")
            self.stop_execution_event.set()
            self.btn_stop_script.configure(
                text="Stopping...", state="disabled")
        else:
            self.update_status_label("No script running to stop.")
            self._reset_execution_buttons_ui()

    def _reset_execution_buttons_ui(self):
        # ... (Giữ nguyên) ...
        if not hasattr(self, 'btn_run_script') or not self.btn_run_script.winfo_exists():
            return
        self.btn_run_script.configure(state="normal")
        self.btn_stop_script.configure(state="disabled", text="⏹️ Stop Script")
        if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
            self.progress_bar.pack_forget()
        if hasattr(self, 'progress_bar_label') and self.progress_bar_label.winfo_exists():
            self.progress_bar_label.pack_forget()

    def _script_execution_worker(self, script_name):
        # ... (Giữ nguyên logic chính, chỉ cần đảm bảo nó gọi đúng _capture_screenshot_for_processing) ...
        # Toàn bộ hàm này gần như giữ nguyên, chỉ thay đổi tên hàm chụp ảnh nếu cần
        try:
            self.update_status_label(
                f"Script '{script_name}': Requesting start from server...")
            start_data = self._make_server_request(
                "POST", f"/api/runtime/scripts/{script_name}/start")
            if self.stop_execution_event.is_set():
                self.update_status_label(
                    f"Script '{script_name}' start cancelled by user.", is_error=True)
                return
            if not start_data or start_data.get("error"):
                err_msg = start_data.get(
                    'error', 'Unknown server error') if start_data else 'No response'
                self.update_status_label(
                    f"Failed to start script '{script_name}': {err_msg}", is_error=True)
                return
            self.current_session_id = start_data.get("session_id")
            self.current_action_details = start_data.get("action")
            required_images = start_data.get("required_images", [])
            initial_message = start_data.get("message", "Script started.")
            self.update_status_label(
                f"'{script_name}': {initial_message} (Session: {self.current_session_id[:8]}...)")
            if not self.current_session_id:
                self.update_status_label(
                    f"No session ID for '{script_name}'. Aborting.", is_error=True)
                return
            if not self.current_action_details and not required_images:
                self.update_status_label(
                    f"Script '{script_name}' empty. Ending.", is_error=True)
                return

            if required_images:
                self.update_status_label(
                    f"Downloading {len(required_images)} images for '{script_name}'...")
                total_images = len(required_images)
                for i, image_name in enumerate(required_images):
                    if self.stop_execution_event.is_set():
                        self.update_status_label(
                            "Image download cancelled.", is_error=True)
                        return
                    self.update_status_label(
                        f"Downloading '{image_name}' ({i+1}/{total_images})...")
                    if not self._ensure_template_image_cached(image_name):
                        self.update_status_label(
                            f"Failed to download/cache '{image_name}'. Stopping.", is_error=True)
                        return
                    if hasattr(self, 'after'):
                        self.after(0, lambda val=(i+1) /
                                   total_images: self.progress_bar.set(val))
                self.update_status_label(
                    f"All {total_images} images ready for '{script_name}'.")
            else:
                self.update_status_label(
                    f"No specific images for '{script_name}', or cached.")

            if hasattr(self, 'after'):
                self.after(0, lambda: self.progress_bar.set(1))
                time.sleep(0.3)
            if hasattr(self, 'after'):
                self.after(0, lambda: [self.progress_bar.pack_forget(
                ), self.progress_bar_label.pack_forget()])

            step_count = 1
            while self.current_action_details and not self.stop_execution_event.is_set():
                instruction_to_execute = self.current_action_details
                instruction_type = instruction_to_execute.get(
                    "type", "Unknown")
                action_note = instruction_to_execute.get("note", "")
                status_prefix = f"'{script_name}' [Step {step_count}]"
                self.update_status_label(
                    f"{status_prefix}: Processing '{instruction_type}' {f'({action_note})' if action_note else ''}")
                execution_result = self._dispatch_server_instruction(
                    instruction_to_execute)
                if self.stop_execution_event.is_set():
                    self.update_status_label(
                        f"{status_prefix}: Stopped by user during '{instruction_type}'.")
                    break
                self.update_status_label(
                    f"{status_prefix}: Instruction '{instruction_type}' result: {'Success' if execution_result.get('success') else 'Failed'}. Notifying server...")
                next_step_data = self._make_server_request("POST", "/api/runtime/scripts/action/next",
                                                           json_data={"session_id": self.current_session_id, "result": execution_result})
                if self.stop_execution_event.is_set():
                    break
                if not next_step_data or next_step_data.get("error"):
                    err_msg = next_step_data.get(
                        'error', 'Unknown server error') if next_step_data else 'No response'
                    self.update_status_label(
                        f"{status_prefix}: Error getting next instruction: {err_msg}", is_error=True)
                    break
                self.current_action_details = next_step_data.get("action")
                server_message = next_step_data.get("message", "Next step...")
                self.update_status_label(
                    f"'{script_name}': Server: \"{server_message}\"")
                if not self.current_action_details:
                    self.update_status_label(
                        f"Script '{script_name}' completed (server).")
                    if hasattr(self, 'after'):
                        self.after(0, lambda: messagebox.showinfo(
                            "Script Complete", f"Script '{script_name}' finished."))
                    break
                step_count += 1
        except Exception as e:
            self.update_status_label(
                f"Critical error in script '{script_name}' worker: {type(e).__name__} - {e}", is_error=True)
            print(f"CRITICAL_WORKER_ERROR: Script '{script_name}': {e}")
        finally:
            # ... (Phần finally giữ nguyên như trước) ...
            final_status_message = f"Script '{script_name}' worker finished."
            if self.stop_execution_event.is_set():
                final_status_message = f"Script '{script_name}' stopped by user."
            elif not self.current_action_details and self.current_session_id:
                final_status_message = f"Script '{script_name}' finished processing."
            if self.current_session_id:
                self.update_status_label(
                    f"{final_status_message} Notifying server to end session {self.current_session_id[:8]}...")
                self._make_server_request(
                    "POST", f"/api/runtime/scripts/session/{self.current_session_id}/stop")
            self.current_session_id = None
            self.current_action_details = None
            if hasattr(self, 'after'):
                self.after(0, self._reset_execution_buttons_ui)
            self.update_status_label(final_status_message)

    def _dispatch_server_instruction(self, instruction_details):
        # ... (Giữ nguyên) ...
        instruction_type = instruction_details.get(
            "type", "Unknown Instruction")
        if self.stop_execution_event.is_set():
            return {"success": False, "error_message": f"Stopped by user before dispatching '{instruction_type}'."}
        if instruction_type == "IF_ELSE_BLOCK":
            return self._execute_if_else_block(instruction_details)
        elif instruction_type == "LOOP_BLOCK":
            return self._execute_loop_block(instruction_details)
        elif instruction_type in ["Click X,Y", "Đợi ảnh xuất hiện", "Tìm ảnh và click", "LOG_MESSAGE"]:
            return self._perform_primitive_action_and_handle_delay(instruction_details)
        else:
            error_msg = f"Unknown instruction type: '{instruction_type}'"
            self.update_status_label(error_msg, is_error=True)
            return {"success": False, "error_message": error_msg, "executed_action_type": instruction_type}

    def _execute_if_else_block(self, block_details):
        # ... (Giữ nguyên) ...
        condition_config = block_details.get("condition")
        then_actions_list = block_details.get("then_actions", [])
        else_actions_list = block_details.get("else_actions", [])
        delay_after_block_ms = int(block_details.get("delay_after_block", 0))
        block_result = {"success": True,
                        "block_type": "IF_ELSE_BLOCK", "details": {}}
        if self.stop_execution_event.is_set():
            block_result["success"] = False
            block_result["error_message"] = "Stopped (before IF eval)."
            return block_result
        self.update_status_label(
            f"  IF_ELSE: Evaluating condition: {condition_config.get('type')} for '{condition_config.get('image', 'N/A')}'...")
        condition_outcome = self._evaluate_condition(condition_config)
        if self.stop_execution_event.is_set():
            block_result["success"] = False
            block_result["error_message"] = "Stopped (after IF eval)."
            block_result["details"]["condition_result"] = condition_outcome
            return block_result
        actions_to_run_in_branch = []
        branch_name_log = ""
        if condition_outcome.get("success"):
            self.update_status_label(
                "  IF_ELSE: Condition TRUE. Executing 'then' branch...")
            actions_to_run_in_branch = then_actions_list
            block_result["details"]["branch_taken"] = "then"
            branch_name_log = "THEN"
        else:
            self.update_status_label(
                f"  IF_ELSE: Condition FALSE (Reason: {condition_outcome.get('error_message', 'N/A')}). Executing 'else' branch...")
            actions_to_run_in_branch = else_actions_list
            block_result["details"]["branch_taken"] = "else"
            branch_name_log = "ELSE"
            if not condition_outcome.get("success"):
                block_result["details"]["condition_evaluation_error"] = condition_outcome.get(
                    "error_message", "Unknown")
        block_result["details"]["condition_raw_result"] = condition_outcome
        for i, sub_action in enumerate(actions_to_run_in_branch):
            if self.stop_execution_event.is_set():
                block_result["success"] = False
                block_result[
                    "error_message"] = f"Stopped during '{branch_name_log}' branch (sub-action {i+1})."
                block_result["details"]["stopped_at_sub_action_index"] = i
                return block_result
            sub_action_type = sub_action.get("type", "Unknown")
            sub_action_note = sub_action.get("note", "")
            self.update_status_label(
                f"    {branch_name_log} Sub-action: '{sub_action_type}' {f'({sub_action_note})' if sub_action_note else ''}")
            sub_action_execution_result = self._dispatch_server_instruction(
                sub_action)
            if not sub_action_execution_result.get("success"):
                block_result["success"] = False
                error_msg = sub_action_execution_result.get(
                    'error_message', f'Sub-action {sub_action_type} failed.')
                block_result["error_message"] = f"Error in '{branch_name_log}' branch: {error_msg}"
                block_result["details"]["failed_sub_action_index"] = i
                block_result["details"]["failed_sub_action_details"] = sub_action_execution_result
                self.update_status_label(
                    f"    Sub-action '{sub_action_type}' in {branch_name_log} FAILED: {error_msg}", is_error=True)
                break
        if not self.stop_execution_event.is_set() and delay_after_block_ms > 0:
            self.update_status_label(
                f"  IF_ELSE_BLOCK branch '{block_result['details']['branch_taken']}' finished. Waiting {delay_after_block_ms}ms...")
            self._sleep_interruptible(delay_after_block_ms)
        return block_result

    def _evaluate_condition(self, condition_config_details):
        # ... (Giữ nguyên) ...
        condition_type = condition_config_details.get("type")
        if self.stop_execution_event.is_set():
            return {"success": False, "error_message": "Stopped (before condition eval)."}
        if condition_type == "IMAGE_EXISTS":
            image_name = condition_config_details.get("image")
            timeout_ms = int(condition_config_details.get("timeout_ms", 1000))
            threshold = float(condition_config_details.get("threshold", 0.8))
            if not image_name:
                return {"success": False, "error_message": "IMAGE_EXISTS: missing image name."}
            template_local_path = os.path.join(self.img_cache_dir, image_name)
            if not os.path.exists(template_local_path):
                self.update_status_label(
                    f"  Cond. img '{image_name}' not cached. Downloading...", is_error=True)
                if not self._ensure_template_image_cached(image_name):
                    return {"success": False, "error_message": f"IMAGE_EXISTS: Failed to get template '{image_name}'."}
            return self._perform_wait_for_image(template_local_path, timeout_ms / 1000, threshold, is_condition_check=True)
        elif condition_type == "ALWAYS_TRUE":
            return {"success": True}
        elif condition_type == "ALWAYS_FALSE":
            return {"success": False, "error_message": "Condition ALWAYS_FALSE."}
        else:
            return {"success": False, "error_message": f"Unsupported condition type: {condition_type}"}

    def _execute_loop_block(self, block_details):
        # ... (Giữ nguyên) ...
        loop_type = block_details.get("loop_type")
        actions_to_run_in_loop = block_details.get("actions_in_loop", [])
        delay_after_block_ms = int(block_details.get("delay_after_block", 0))
        delay_between_iterations_ms = int(
            block_details.get("delay_between_iterations_ms", 200))
        block_result = {"success": True, "block_type": "LOOP_BLOCK",
                        "details": {"iterations_completed": 0}}
        if self.stop_execution_event.is_set():
            block_result["success"] = False
            block_result["error_message"] = "Stopped (before LOOP)."
            return block_result

        if loop_type == "COUNT":
            count = int(block_details.get("count", 1))
            self.update_status_label(
                f"  LOOP (COUNT): Starting for {count} iterations...")
            for i in range(count):
                if self.stop_execution_event.is_set():
                    block_result["success"] = False
                    block_result["error_message"] = f"Stopped in COUNT loop iter {i+1}."
                    break
                self.update_status_label(f"    Loop iteration {i+1}/{count}:")
                block_result["details"]["iterations_completed"] = i + 1
                for j, sub_action in enumerate(actions_to_run_in_loop):
                    if self.stop_execution_event.is_set():
                        block_result["success"] = False
                        block_result[
                            "error_message"] = f"Stopped in sub-action of loop iter {i+1}."
                        return block_result
                    current_sub_action_data = dict(sub_action)
                    if "message" in current_sub_action_data and isinstance(current_sub_action_data["message"], str):
                        current_sub_action_data["message"] = current_sub_action_data["message"].replace(
                            "{loop_iteration}", str(i+1))
                    if "note" in current_sub_action_data and isinstance(current_sub_action_data["note"], str):
                        current_sub_action_data["note"] = current_sub_action_data["note"].replace(
                            "{loop_iteration}", str(i+1))
                    sub_action_type = current_sub_action_data.get(
                        "type", "Unknown")
                    processed_note = current_sub_action_data.get("note", "")
                    self.update_status_label(
                        f"      Loop Sub-action: '{sub_action_type}' {f'({processed_note})' if processed_note else ''}")
                    single_action_execution_result = self._dispatch_server_instruction(
                        current_sub_action_data)
                    if not single_action_execution_result.get("success"):
                        block_result["success"] = False
                        error_msg = single_action_execution_result.get(
                            'error_message', f'Sub-action {sub_action_type} in loop failed.')
                        block_result["error_message"] = error_msg
                        block_result["details"]["failed_at_iteration"] = i + 1
                        block_result["details"]["failed_sub_action_index"] = j
                        self.update_status_label(
                            f"      Sub-action '{sub_action_type}' in loop FAILED: {error_msg}", is_error=True)
                        return block_result
                if i < count - 1 and not self.stop_execution_event.is_set() and delay_between_iterations_ms > 0:
                    self.update_status_label(
                        f"    End of iteration {i+1}. Waiting {delay_between_iterations_ms}ms...")
                    self._sleep_interruptible(delay_between_iterations_ms)
        else:
            block_result["success"] = False
            block_result["error_message"] = f"Unsupported loop type: {loop_type}"
            self.update_status_label(
                block_result["error_message"], is_error=True)

        if not self.stop_execution_event.is_set() and delay_after_block_ms > 0 and block_result["success"]:
            self.update_status_label(
                f"  LOOP_BLOCK '{loop_type}' finished. Waiting {delay_after_block_ms}ms...")
            self._sleep_interruptible(delay_after_block_ms)
        return block_result

    def _perform_primitive_action_and_handle_delay(self, action_details):
        # ... (Giữ nguyên như phiên bản trước) ...
        action_type = action_details.get("type", "Unknown Type")
        detail_str = action_details.get("details")
        image_name = action_details.get("image")
        delay_after_action_ms = int(action_details.get("delay", 500))
        action_result_dict = {"success": False,
                              "executed_action_type": action_type}
        template_local_path = None
        if image_name:
            template_local_path = os.path.join(self.img_cache_dir, image_name)
            if not os.path.exists(template_local_path):
                action_result_dict["error_message"] = f"FATAL: Image '{image_name}' not cached."
                return action_result_dict
        if self.stop_execution_event.is_set():
            action_result_dict["error_message"] = "Stopped before primitive action."
            return action_result_dict
        if action_type == "Click X,Y":
            action_result_dict = self._perform_click_xy(detail_str)
        elif action_type == "Đợi ảnh xuất hiện":
            timeout_ms_for_wait = int(action_details.get("delay", 5000))
            action_result_dict = self._perform_wait_for_image(
                template_local_path, timeout_ms_for_wait / 1000)
            delay_after_action_ms = 200
        elif action_type == "Tìm ảnh và click":
            action_result_dict = self._perform_find_image_and_click(
                template_local_path)
        elif action_type == "LOG_MESSAGE":
            log_msg = action_details.get("message", "No log message.")
            self.update_status_label(f"CLIENT SCRIPT LOG: {log_msg}")
            action_result_dict = {"success": True}
        else:
            action_result_dict[
                "error_message"] = f"Unsupported primitive action: '{action_type}'"
        action_result_dict["executed_action_type"] = action_type
        if not self.stop_execution_event.is_set() and delay_after_action_ms > 0:
            # LOG_MESSAGE không có 'success'
            status_msg = f"  Primitive '{action_type}' {'OK' if action_result_dict.get('success', True) else 'FAIL'}. "
            if not action_result_dict.get('success', True) and "error_message" in action_result_dict:
                status_msg += f"Err: {action_result_dict['error_message']}. "
            status_msg += f"Wait {delay_after_action_ms}ms..."
            self.update_status_label(
                status_msg, is_error=not action_result_dict.get('success', True))
            self._sleep_interruptible(delay_after_action_ms)
        return action_result_dict

    def _sleep_interruptible(self, duration_ms):
        # ... (Giữ nguyên) ...
        if duration_ms <= 0:
            return
        sleep_interval_s = 0.05
        end_time = time.time() + duration_ms / 1000.0
        while time.time() < end_time:
            if self.stop_execution_event.is_set():
                break
            actual_sleep = min(sleep_interval_s, end_time - time.time())
            if actual_sleep <= 0:
                break
            time.sleep(actual_sleep)

    def _ensure_template_image_cached(self, image_name_on_server):
        # ... (Giữ nguyên) ...
        local_image_path = os.path.join(
            self.img_cache_dir, image_name_on_server)
        if os.path.exists(local_image_path):
            return True
        try:
            response = self._make_server_request(
                "GET", f"/api/runtime/images/{image_name_on_server}", stream=True, timeout=30)
            if not response or response.get("error"):
                error_detail = response.get(
                    "error", "Unknown") if response else "No response"
                self.update_status_label(
                    f"Download init failed for '{image_name_on_server}'. Server: {error_detail}", is_error=True)
                return False
            if not hasattr(response, 'iter_content'):
                self.update_status_label(
                    f"Download for '{image_name_on_server}' failed: Not a stream response.", is_error=True)
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
                f"Critical download error for '{image_name_on_server}': {type(e).__name__} - {e}", is_error=True)
            if os.path.exists(local_image_path):
                try:
                    os.remove(local_image_path)
                except OSError:
                    pass
            return False

    # Đổi tên hàm này để chỉ làm nhiệm vụ chụp và trả về CV2 image
    def _capture_screenshot_for_processing(self):
        if self.stop_execution_event.is_set():
            # self.update_status_label("Screenshot capture skipped (stop request).") # Không cần log nhiều
            return None
        success, screenshot_path_on_client = self.controller.capture()
        if not success:
            self.update_status_label(
                f"Failed to capture screenshot. ADB: {screenshot_path_on_client}", is_error=True)
            return None
        if not os.path.exists(screenshot_path_on_client):
            self.update_status_label(
                f"Screenshot file '{screenshot_path_on_client}' missing after capture.", is_error=True)
            return None
        try:
            screenshot_cv = cv2.imread(screenshot_path_on_client)
            if screenshot_cv is None:
                self.update_status_label(
                    f"Failed to read '{screenshot_path_on_client}' (OpenCV).", is_error=True)
                return None
            return screenshot_cv
        except Exception as e:
            self.update_status_label(
                f"Error processing screenshot file '{screenshot_path_on_client}': {e}", is_error=True)
            return None

    def _perform_click_xy(self, detail_str):
        # ... (Giữ nguyên) ...
        result = {"success": False}
        if not detail_str:
            result["error_message"] = "Click X,Y: no details string."
            return result
        try:
            parts = [p.strip() for p in detail_str.split(',')]
            x_str = parts[0].split(':')[1].strip()
            y_str = parts[1].split(':')[1].strip()
            x = int(x_str)
            y = int(y_str)
            if self.stop_execution_event.is_set():
                result["error_message"] = "Stopped (before click)."
                return result
            success_click, msg = self.controller.click(x, y)
            result["success"] = success_click
            if not success_click:
                result["error_message"] = msg or "Click failed."
            return result
        except Exception as e:
            result["error_message"] = f"Invalid X,Y details '{detail_str}'. Err: {e}"
            return result

    def _perform_wait_for_image(self, template_local_path, timeout_seconds, threshold=0.8, is_condition_check=False):
        # ... (Giữ nguyên, nhưng sử dụng _capture_screenshot_for_processing) ...
        result = {"success": False}
        if not template_local_path or not os.path.exists(template_local_path):
            result["error_message"] = f"Template missing: {template_local_path}"
            return result
        template_cv = cv2.imread(template_local_path)
        if template_cv is None:
            result["error_message"] = f"Cannot read template: {template_local_path}"
            return result
        start_time = time.time()
        image_basename = os.path.basename(template_local_path)
        max_val_conf = 0.0  # Theo dõi confidence cao nhất tìm được
        while time.time() - start_time < timeout_seconds:
            if self.stop_execution_event.is_set():
                result["error_message"] = f"Stopped during wait for '{image_basename}'."
                return result
            screenshot_cv = self._capture_screenshot_for_processing()  # Sử dụng hàm mới
            if screenshot_cv is None:
                time.sleep(0.5)
                continue
            try:
                res = cv2.matchTemplate(
                    screenshot_cv, template_cv, cv2.TM_CCOEFF_NORMED)
                min_val, current_max_conf, min_loc, max_loc_coords = cv2.minMaxLoc(
                    res)
                if current_max_conf > max_val_conf:
                    max_val_conf = current_max_conf  # Cập nhật conf cao nhất
            except cv2.error as e:
                result["error_message"] = f"OpenCV match error for '{image_basename}': {e}."
                time.sleep(0.5)
                continue
            if max_val_conf >= threshold:
                result["success"] = True
                pt_x, pt_y = int(max_loc_coords[0]), int(max_loc_coords[1])
                h, w = template_cv.shape[:2]
                result["found_at_raw"] = {"x": pt_x, "y": pt_y}
                result["template_size"] = {"width": w, "height": h}
                result["match_confidence"] = float(max_val_conf)
                return result
            time.sleep(0.25)
        if not self.stop_execution_event.is_set():
            result[
                "error_message"] = f"Timeout waiting for '{image_basename}'. Max conf: {max_val_conf:.2f} (Thresh: {threshold})"
        return result

    def _perform_find_image_and_click(self, template_local_path, threshold=0.8):
        # ... (Giữ nguyên, nhưng sử dụng _capture_screenshot_for_processing) ...
        result = {"success": False}
        if not template_local_path or not os.path.exists(template_local_path):
            result["error_message"] = f"Template missing: {template_local_path}"
            return result
        template_cv = cv2.imread(template_local_path)
        if template_cv is None:
            result["error_message"] = f"Cannot read template: {template_local_path}"
            return result
        if self.stop_execution_event.is_set():
            result["error_message"] = "Stopped (before find/click)."
            return result
        screenshot_cv = self._capture_screenshot_for_processing()  # Sử dụng hàm mới
        if screenshot_cv is None:
            result["error_message"] = "Failed to capture screenshot for find/click."
            return result
        image_basename = os.path.basename(template_local_path)
        try:
            res = cv2.matchTemplate(
                screenshot_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc_coords = cv2.minMaxLoc(res)
        except cv2.error as e:
            result["error_message"] = f"OpenCV match error for '{image_basename}': {e}."
            return result
        if max_val >= threshold:
            pt_x, pt_y = max_loc_coords
            h, w = template_cv.shape[:2]
            center_x = pt_x + w // 2
            center_y = pt_y + h // 2
            result["found_at_raw"] = {"x": int(pt_x), "y": int(pt_y)}
            result["template_size"] = {"width": w, "height": h}
            result["match_confidence"] = float(max_val)
            if self.stop_execution_event.is_set():
                result["error_message"] = "Stopped after find, before click."
                result["success"] = False
                return result
            success_click, msg = self.controller.click(center_x, center_y)
            result["success"] = success_click
            if success_click:
                result["clicked_at"] = {"x": center_x, "y": center_y}
            else:
                result["error_message"] = msg or "Click failed after find."
        else:
            result["success"] = False
            result["error_message"] = f"'{image_basename}' not found (max conf: {max_val:.2f} < thresh {threshold})."
        return result

    def on_closing(self):
        # ... (Giữ nguyên) ...
        self.request_stop_script_execution()
        if self.execution_thread and self.execution_thread.is_alive():
            self.update_status_label(
                "Window closing. Waiting for execution thread...")
            self.execution_thread.join(timeout=2.0)
            if self.execution_thread.is_alive():
                self.update_status_label(
                    "Exec thread did not stop in time. Forcing exit.", is_error=True)
        self.destroy()
