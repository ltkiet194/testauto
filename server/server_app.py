from flask import Flask, jsonify, request, render_template, send_from_directory
import os
import json
import uuid
import time

app = Flask(__name__)

# Sử dụng đường dẫn tuyệt đối
BASE_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
# Thư mục chứa script do người dùng tạo/chỉnh sửa (cho cả designer và runtime)
USER_SCRIPTS_DIR = os.path.join(BASE_SERVER_DIR, "scripts_user")
# Thư mục chứa ảnh mẫu dùng chung
IMAGES_DIR = os.path.join(BASE_SERVER_DIR, "img")
# Thư mục chứa template HTML cho designer (nếu có)
TEMPLATE_DIR = os.path.join(BASE_SERVER_DIR, "templates")
# Đảm bảo thư mục template tồn tại nếu Flask cần
if not os.path.exists(TEMPLATE_DIR):
    os.makedirs(TEMPLATE_DIR)
    print(f"Created missing templates directory: {TEMPLATE_DIR}")
app.template_folder = TEMPLATE_DIR  # Chỉ định rõ thư mục template

# { "session_id": {"script_name": "abc", "current_step_index": 0, "script_data": [...], "variables": {}} }
client_runtime_sessions = {}  # Đổi tên để rõ ràng là của runtime client

# --- Dữ liệu cấu hình cho Designer (và để server biết cấu trúc) ---
AVAILABLE_ACTIONS_CONFIG = [
    {
        "type": "LOG_MESSAGE", "displayName": "Log Message", "isBlock": False,
        "defaultNote": "Log a message on client",
        "params": [
            {"name": "message", "label": "Message to log",
                "type": "textarea", "defaultValue": "Log entry"},
            {"name": "delay",
                "label": "Delay after (ms)", "type": "number", "defaultValue": 500}
        ]
    },
    {
        "type": "Click X,Y", "displayName": "Click X,Y", "isBlock": False,
        "defaultNote": "Click at specific coordinates",
        "params": [
            {"name": "details",
                "label": "Coordinates (e.g., X:100,Y:200)", "type": "text", "defaultValue": "X:0,Y:0"},
            {"name": "delay",
                "label": "Delay after (ms)", "type": "number", "defaultValue": 1000}
        ]
    },
    {
        "type": "Đợi ảnh xuất hiện", "displayName": "Wait for Image", "isBlock": False,
        "defaultNote": "Wait for an image to appear",
        "params": [
            {"name": "image", "label": "Image Filename",
                "type": "select-image", "defaultValue": ""},
            {"name": "delay",
                "label": "Timeout (ms)", "type": "number", "defaultValue": 5000},
            {"name": "threshold", "label": "Threshold (0-1)", "type": "number", "defaultValue": 0.8, "inputAttributes": {
                "step": 0.01, "min": 0, "max": 1}}
        ]
    },
    {
        "type": "Tìm ảnh và click", "displayName": "Find Image & Click", "isBlock": False,
        "defaultNote": "Find an image and click its center",
        "params": [
            {"name": "image", "label": "Image Filename",
                "type": "select-image", "defaultValue": ""},
            {"name": "delay",
                "label": "Delay after click (ms)", "type": "number", "defaultValue": 1000},
            {"name": "threshold", "label": "Threshold (0-1)", "type": "number", "defaultValue": 0.8, "inputAttributes": {
                "step": 0.01, "min": 0, "max": 1}}
        ]
    },
    {
        "type": "IF_ELSE_BLOCK", "displayName": "IF-ELSE Block", "isBlock": True,
        "defaultNote": "Conditional execution block",
        "conditionTypes": [
            {"value": "IMAGE_EXISTS", "text": "Image Exists on Screen"},
            {"value": "ALWAYS_TRUE", "text": "Always True (for testing)"},
            {"value": "ALWAYS_FALSE", "text": "Always False (for testing)"}
        ],
        "defaultConditionType": "IMAGE_EXISTS",
        "params": [
            {"name": "delay_after_block",
                "label": "Delay after block (ms)", "type": "number", "defaultValue": 500}
        ]
    },
    {
        "type": "LOOP_BLOCK", "displayName": "LOOP Block", "isBlock": True,
        "defaultNote": "Loop execution block",
        "loopTypes": [
            {"value": "COUNT", "text": "Fixed Count Loop"},
        ],
        "defaultLoopType": "COUNT",
        "defaultCount": 3,
        "params": [
            {"name": "delay_between_iterations_ms",
                "label": "Delay between iterations (ms)", "type": "number", "defaultValue": 200},
            {"name": "delay_after_block",
                "label": "Delay after block (ms)", "type": "number", "defaultValue": 500}
        ]
    }
]


def initialize_server_directories_and_samples():
    """Khởi tạo thư mục và file mẫu nếu chưa có."""
    if not os.path.exists(USER_SCRIPTS_DIR):
        os.makedirs(USER_SCRIPTS_DIR)
        print(f"Created user scripts directory: {USER_SCRIPTS_DIR}")
        sample_script_content = [
            {"type": "LOG_MESSAGE", "message": "Đây là kịch bản mẫu từ server.",
                "delay": 500, "note": "Bắt đầu"},
            {"type": "IF_ELSE_BLOCK", "note": "Kiểm tra ảnh mẫu 1",
             "condition": {"type": "IMAGE_EXISTS", "image": "sample_image1.png", "timeout_ms": 1000},
             "then_actions": [{"type": "LOG_MESSAGE", "message": "Ảnh mẫu 1 tồn tại.", "delay": 200}],
             "else_actions": [{"type": "LOG_MESSAGE", "message": "Ảnh mẫu 1 KHÔNG tồn tại.", "delay": 200}],
             "delay_after_block": 100
             },
            {"type": "LOG_MESSAGE", "message": "Kịch bản mẫu kết thúc.", "delay": 500}
        ]
        try:
            with open(os.path.join(USER_SCRIPTS_DIR, "sample_server_script.json"), "w", encoding="utf-8") as f:
                json.dump(sample_script_content, f,
                          indent=2, ensure_ascii=False)
            print(f"Created sample_server_script.json in {USER_SCRIPTS_DIR}")
        except IOError as e:
            print(f"Error creating sample_server_script.json: {e}")

    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        print(f"Created shared images directory: {IMAGES_DIR}")
        try:
            from PIL import Image, ImageDraw, ImageFont
            try:
                font = ImageFont.truetype("arial.ttf", 10)
            except IOError:
                font = ImageFont.load_default()

            for i, img_name in enumerate(["sample_image1.png", "sample_image2.png"]):
                img_path = os.path.join(IMAGES_DIR, img_name)
                if not os.path.exists(img_path):  # Chỉ tạo nếu chưa có
                    try:
                        img = Image.new('RGB', (120, 60), color=(
                            '#4A90E2' if i == 0 else '#D0021B'))
                        draw = ImageDraw.Draw(img)
                        text = img_name.split('.')[0]
                        draw.text((5, 5), text, fill=('#FFFFFF'), font=font)
                        img.save(img_path)
                    except Exception as e_img:
                        print(
                            f"Error creating sample image {img_name}: {e_img}.")
            print(f"Checked/created sample images in {IMAGES_DIR}.")
        except ImportError:
            print(
                "Pillow library not found. Sample images may not be created automatically.")
        except Exception as e_pil:
            print(
                f"An error occurred with Pillow while creating sample images: {e_pil}")


initialize_server_directories_and_samples()

# --- Route cho trang Designer (nếu bạn có) ---


@app.route('/designer')
def script_designer_page_route():  # Đổi tên hàm để tránh trùng
    return render_template('script_designer.html')


# --- API Endpoints cho Designer ---
DESIGNER_API_PREFIX = '/api/designer'


@app.route(f'{DESIGNER_API_PREFIX}/actions', methods=['GET'])
def designer_get_available_actions():
    return jsonify(AVAILABLE_ACTIONS_CONFIG)


@app.route(f'{DESIGNER_API_PREFIX}/images', methods=['GET'])
def designer_get_available_images():
    try:
        if not os.path.exists(IMAGES_DIR):
            return jsonify([])
        images = [f for f in os.listdir(
            IMAGES_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        return jsonify(sorted(images))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route(f'{DESIGNER_API_PREFIX}/scripts', methods=['GET'])
def designer_list_user_scripts():
    try:
        if not os.path.exists(USER_SCRIPTS_DIR):
            return jsonify([])
        scripts = [f.replace('.json', '') for f in os.listdir(
            USER_SCRIPTS_DIR) if f.endswith('.json')]
        return jsonify(sorted(scripts))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route(f'{DESIGNER_API_PREFIX}/scripts/<script_name>', methods=['GET'])
def designer_get_user_script(script_name):
    safe_script_name = "".join(
        c for c in script_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    if not safe_script_name:
        return jsonify({"error": "Invalid script name"}), 400
    script_path = os.path.join(USER_SCRIPTS_DIR, f"{safe_script_name}.json")
    if os.path.exists(script_path):
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception as e:
            return jsonify({"error": f"Error reading script: {str(e)}"}), 500
    else:
        return jsonify({"error": "Script not found"}), 404


@app.route(f'{DESIGNER_API_PREFIX}/scripts/<script_name>', methods=['POST'])
def designer_save_user_script(script_name):
    safe_script_name = "".join(
        c for c in script_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    if not safe_script_name:
        return jsonify({"error": "Invalid script name"}), 400
    script_data = request.get_json()
    if not isinstance(script_data, list):
        return jsonify({"error": "Invalid script data format."}), 400
    script_path = os.path.join(USER_SCRIPTS_DIR, f"{safe_script_name}.json")
    try:
        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script_data, f, indent=2, ensure_ascii=False)
        return jsonify({"message": f"Script '{safe_script_name}' saved."})
    except Exception as e:
        return jsonify({"error": f"Error saving script: {str(e)}"}), 500


# --- API Endpoints cho Client Runtime ---
CLIENT_RUNTIME_API_PREFIX = '/api/runtime'


# Thêm Ping cho runtime
@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/ping', methods=['GET'])
def runtime_ping():
    return jsonify({"message": "pong_runtime", "timestamp": time.time()})


@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/scripts', methods=['GET'])
def runtime_list_scripts():
    print(
        f"RUNTIME API: Request for /scripts received. Serving from: {USER_SCRIPTS_DIR}")
    try:
        if not os.path.exists(USER_SCRIPTS_DIR):
            print(
                f"RUNTIME API: Scripts directory not found: {USER_SCRIPTS_DIR}")
            return jsonify([])
        scripts = [f.replace('.json', '') for f in os.listdir(
            USER_SCRIPTS_DIR) if f.endswith('.json')]
        print(f"RUNTIME API: Found scripts: {scripts}")
        return jsonify(sorted(scripts))
    except Exception as e:
        print(f"RUNTIME API: Error listing scripts: {e}")
        return jsonify({"error": f"Server error listing scripts for runtime: {str(e)}"}), 500


@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/images/<path:image_name>', methods=['GET'])
def runtime_get_image(image_name):
    print(f"RUNTIME API: Request for image '{image_name}'")
    try:
        if not os.path.exists(IMAGES_DIR):
            return jsonify({"error": f"Images directory not found: {IMAGES_DIR}"}), 500
        safe_image_name = os.path.normpath(image_name).lstrip('./\\')
        if safe_image_name != image_name:
            return jsonify({"error": "Invalid image path"}), 400
        return send_from_directory(IMAGES_DIR, safe_image_name, as_attachment=True)
    except FileNotFoundError:
        print(f"RUNTIME API: Image not found: {image_name} in {IMAGES_DIR}")
        return jsonify({"error": f"Image '{image_name}' not found on server"}), 404
    except Exception as e:
        print(f"RUNTIME API: Error serving image {image_name}: {e}")
        return jsonify({"error": f"Server error serving image: {str(e)}"}), 500


@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/scripts/<script_name>/start', methods=['POST'])
def runtime_start_script_session(script_name):
    safe_script_name = "".join(
        c for c in script_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    script_path = os.path.join(USER_SCRIPTS_DIR, f"{safe_script_name}.json")

    print(
        f"RUNTIME API: Request to start script '{safe_script_name}' from path '{script_path}'")

    if not os.path.exists(script_path):
        print(f"RUNTIME API: Script not found: {safe_script_name}")
        return jsonify({"error": f"Script '{safe_script_name}' not found"}), 404

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_data = json.load(f)
        if not isinstance(script_data, list) or not script_data:  # Kiểm tra script_data rỗng
            print(
                f"RUNTIME API: Script '{safe_script_name}' is empty or has invalid format.")
            # Trả về action: None nếu script rỗng để client biết kết thúc sớm
            # Nếu là list rỗng
            if not script_data and isinstance(script_data, list):
                session_id_empty = str(uuid.uuid4())
                client_runtime_sessions[session_id_empty] = {  # Vẫn tạo session để client có thể stop
                    "script_name": safe_script_name, "current_step_index": 0,
                    "script_data": [], "variables": {}, "max_steps": 0
                }
                print(
                    f"Runtime Session {session_id_empty} for EMPTY script '{safe_script_name}'.")
                return jsonify({
                    "session_id": session_id_empty, "action": None, "required_images": [],
                    "message": f"Script '{safe_script_name}' is empty. Nothing to execute."
                })
            return jsonify({"error": "Script has invalid format (not a list)."}), 400
    except Exception as e:
        print(f"RUNTIME API: Error reading script '{safe_script_name}': {e}")
        return jsonify({"error": f"Error reading script data: {str(e)}"}), 500

    session_id = str(uuid.uuid4())
    required_images = sorted(list(set(
        action_detail["image"]
        for action_detail in script_data
        if isinstance(action_detail, dict) and action_detail.get("image")
    )))

    client_runtime_sessions[session_id] = {
        "script_name": safe_script_name, "current_step_index": 0,
        "script_data": script_data, "variables": {}, "max_steps": len(script_data)
    }

    # Script_data đã được đảm bảo không rỗng ở đây
    first_action = script_data[0]
    print(
        f"Runtime Session {session_id} started for script '{safe_script_name}'. Required images: {required_images}. Sending first action.")
    return jsonify({
        "session_id": session_id, "action": first_action,
        "required_images": required_images,
        "message": f"Script '{safe_script_name}' started. Session: {session_id[:8]}..."
    })


@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/scripts/action/next', methods=['POST'])
def runtime_get_next_action():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request: No JSON data."}), 400
    session_id = data.get('session_id')
    last_action_result = data.get(
        'result', {"success": False, "error_message": "No result from client"})

    if not session_id or session_id not in client_runtime_sessions:
        print(
            f"RUNTIME API: Invalid/expired session ID for next_action: {session_id}")
        return jsonify({"error": "Invalid or expired session ID"}), 400

    session = client_runtime_sessions[session_id]
    executed_step_idx = session['current_step_index']
    print(
        f"Runtime Session {session_id}, Script '{session['script_name']}', Result for step {executed_step_idx + 1}: {last_action_result}")

    session["current_step_index"] += 1
    if session["current_step_index"] >= session["max_steps"]:
        print(
            f"Runtime: Script '{session['script_name']}' (Session {session_id}) completed.")
        if session_id in client_runtime_sessions:
            del client_runtime_sessions[session_id]
        return jsonify({"session_id": session_id, "action": None, "message": "Script completed."})

    next_action_detail = session["script_data"][session["current_step_index"]]
    print(
        f"Runtime Session {session_id}, sending next action (Step {session['current_step_index'] + 1}/{session['max_steps']}): Type '{next_action_detail.get('type', 'N/A')}'")
    return jsonify({
        "session_id": session_id, "action": next_action_detail,
        "message": f"Proceed with action for step {session['current_step_index'] + 1}."
    })


@app.route(f'{CLIENT_RUNTIME_API_PREFIX}/scripts/session/<session_id>/stop', methods=['POST'])
def runtime_stop_script_session(session_id):
    if session_id in client_runtime_sessions:
        script_name = client_runtime_sessions[session_id]["script_name"]
        del client_runtime_sessions[session_id]
        print(
            f"Runtime Session {session_id} for script '{script_name}' stopped by client.")
        return jsonify({"message": f"Session for '{script_name}' stopped by your request."})
    else:
        print(f"Runtime: Attempted to stop non-existent session: {session_id}")
        return jsonify({"error": "Session not found or already stopped on server."}), 404


if __name__ == '__main__':
    print(f"ADB Script Server starting...")
    print(f" * Designer UI (if script_designer.html exists): http://localhost:5000/designer")
    print(f" * User scripts directory: {USER_SCRIPTS_DIR}")
    print(f" * Shared images directory: {IMAGES_DIR}")
    print(f" * Runtime API Prefix: {CLIENT_RUNTIME_API_PREFIX}")
    print(f" * Designer API Prefix: {DESIGNER_API_PREFIX}")

    # Liệt kê các script có sẵn khi khởi động
    try:
        startup_scripts = [f.replace('.json', '') for f in os.listdir(
            USER_SCRIPTS_DIR) if f.endswith('.json')]
        print(
            f" * Available scripts for runtime at startup: {startup_scripts if startup_scripts else 'None'}")
    except FileNotFoundError:
        print(
            f" * User scripts directory {USER_SCRIPTS_DIR} not found at startup. It will be created.")
    except Exception as e:
        print(f" * Error listing startup scripts: {e}")

    # use_reloader=True là mặc định khi debug=True
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True)
