from flask import Flask, jsonify, request, send_from_directory
import os
import json
import uuid
import time

app = Flask(__name__)

# Sử dụng đường dẫn tuyệt đối
BASE_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_SERVER_DIR, "scripts")
IMAGES_DIR = os.path.join(BASE_SERVER_DIR, "img")

# { "session_id": {"script_name": "abc", "current_step_index": 0, "script_data": [...], "variables": {}} }
client_sessions = {}


def initialize_server_directories():
    """Khởi tạo thư mục và file mẫu nếu chưa có."""
    if not os.path.exists(SCRIPTS_DIR):
        os.makedirs(SCRIPTS_DIR)
        print(f"Created directory: {SCRIPTS_DIR}")
        sample_script_content = [
            {"type": "Đợi ảnh xuất hiện", "image": "sample_image1.png", "delay": 5000,
                "note": "Đợi ảnh 'sample_image1.png' xuất hiện (timeout 5s)"},
            {"type": "Tìm ảnh và click", "image": "sample_image1.png", "delay": 1000,
                "note": "Tìm và click 'sample_image1.png', sau đó đợi 1s"},
            {"type": "Click X,Y", "details": "X: 100, Y: 200", "delay": 1500,
                "note": "Click tọa độ (100,200), sau đó đợi 1.5s"},
            {"type": "Đợi ảnh xuất hiện", "image": "sample_image2.png",
                "delay": 3000, "note": "Đợi ảnh 'sample_image2.png' (timeout 3s)"}
        ]
        try:
            with open(os.path.join(SCRIPTS_DIR, "sample_script.json"), "w", encoding="utf-8") as f:
                json.dump(sample_script_content, f,
                          indent=2, ensure_ascii=False)
            print(f"Created sample_script.json in {SCRIPTS_DIR}")
        except IOError as e:
            print(f"Error creating sample_script.json: {e}")

    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        print(f"Created directory: {IMAGES_DIR}")
        try:
            from PIL import Image, ImageDraw, ImageFont
            # Cố gắng tìm một font cơ bản, nếu không có thì bỏ qua text
            try:
                font = ImageFont.truetype("arial.ttf", 10)
            except IOError:
                font = ImageFont.load_default()

            for i, img_name in enumerate(["sample_image1.png", "sample_image2.png"]):
                img_path = os.path.join(IMAGES_DIR, img_name)
                try:
                    img = Image.new('RGB', (120, 60), color=(
                        '#4A90E2' if i == 0 else '#D0021B'))  # Blue and Red
                    draw = ImageDraw.Draw(img)
                    text = img_name.split('.')[0]
                    # Đơn giản hóa text để vừa ảnh nhỏ
                    draw.text((5, 5), text, fill=('#FFFFFF'), font=font)
                    img.save(img_path)
                except Exception as e_img:  # Bắt lỗi cụ thể khi tạo ảnh
                    print(
                        f"Error creating sample image {img_name}: {e_img}. Please create it manually.")
            print(
                f"Created sample images in {IMAGES_DIR} (if Pillow is available and no errors occurred).")
        except ImportError:
            print("Pillow library not found. Cannot create sample images. Please create them manually in 'server/img/' for testing.")
        except Exception as e_pil:  # Bắt lỗi chung khi import hoặc dùng Pillow
            print(
                f"An error occurred with Pillow while creating sample images: {e_pil}")


@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"message": "pong", "timestamp": time.time()})


@app.route('/api/scripts', methods=['GET'])
def list_scripts():
    try:
        if not os.path.exists(SCRIPTS_DIR):
            return jsonify({"error": f"Scripts directory not found: {SCRIPTS_DIR}"}), 500
        scripts = [f.replace('.json', '') for f in os.listdir(
            SCRIPTS_DIR) if f.endswith('.json')]
        return jsonify(scripts)
    except Exception as e:
        print(f"Error listing scripts: {e}")
        return jsonify({"error": f"Server error listing scripts: {str(e)}"}), 500


@app.route('/api/images/<path:image_name>', methods=['GET'])
def get_image(image_name):
    try:
        if not os.path.exists(IMAGES_DIR):
            return jsonify({"error": f"Images directory not found: {IMAGES_DIR}"}), 500
        # Chống path traversal, dù send_from_directory đã an toàn
        safe_image_name = os.path.normpath(image_name).lstrip('./\\')
        if safe_image_name != image_name:  # Chỉ cho phép tên file, không cho phép ../
            return jsonify({"error": "Invalid image path"}), 400

        return send_from_directory(IMAGES_DIR, safe_image_name, as_attachment=True)
    except FileNotFoundError:
        print(f"Image not found: {image_name} in {IMAGES_DIR}")
        return jsonify({"error": f"Image '{image_name}' not found on server"}), 404
    except Exception as e:
        print(f"Error serving image {image_name}: {e}")
        return jsonify({"error": f"Server error serving image: {str(e)}"}), 500


@app.route('/api/scripts/<script_name>/start', methods=['POST'])
def start_script_session(script_name):
    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.json")
    if not os.path.exists(script_path):
        print(f"Script not found: {script_name} at {script_path}")
        return jsonify({"error": f"Script '{script_name}' not found"}), 404

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_data = json.load(f)
        if not isinstance(script_data, list) or not script_data:
            print(f"Script '{script_name}' is empty or has invalid format.")
            return jsonify({"error": "Script is empty or has invalid format"}), 400
    except Exception as e:
        print(f"Error reading script '{script_name}': {e}")
        return jsonify({"error": f"Error reading script data: {str(e)}"}), 500

    session_id = str(uuid.uuid4())

    required_images = sorted(list(set(
        action_detail["image"]
        for action_detail in script_data
        if isinstance(action_detail, dict) and action_detail.get("image")
    )))

    client_sessions[session_id] = {
        "script_name": script_name,
        "current_step_index": 0,
        "script_data": script_data,
        "variables": {},
        "max_steps": len(script_data)
    }

    first_action = script_data[0]
    print(f"Session {session_id} started for script '{script_name}'. Required images: {required_images}. Sending first action.")
    return jsonify({
        "session_id": session_id,
        "action": first_action,
        "required_images": required_images,
        "message": f"Script '{script_name}' started. Session: {session_id[:8]}..."
    })


@app.route('/api/scripts/action/next', methods=['POST'])
def get_next_action():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request: No JSON data received."}), 400

    session_id = data.get('session_id')
    last_action_result = data.get(
        'result', {"success": False, "error_message": "No result provided by client"})

    if not session_id or session_id not in client_sessions:
        print(f"Invalid or expired session ID received: {session_id}")
        return jsonify({"error": "Invalid or expired session ID"}), 400

    session = client_sessions[session_id]
    current_step_executed_index = session['current_step_index']

    print(f"Session {session_id}, Script '{session['script_name']}', "
          f"Result for step {current_step_executed_index + 1}: {last_action_result}")

    # --- ADVANCED LOGIC (OPTIONAL): ---
    # current_action_config = session["script_data"][current_step_executed_index]
    # if not last_action_result.get("success"):
    #     on_fail_config = current_action_config.get("on_fail")
    #     if isinstance(on_fail_config, dict) and "goto_step_label" in on_fail_config:
    #         # Tìm label và nhảy tới đó (cần thêm logic tìm label)
    #         pass

    session["current_step_index"] += 1

    if session["current_step_index"] >= session["max_steps"]:
        print(
            f"Script '{session['script_name']}' (Session {session_id}) completed all steps.")
        if session_id in client_sessions:
            del client_sessions[session_id]
        return jsonify({"session_id": session_id, "action": None, "message": "Script completed."})

    next_action_detail = session["script_data"][session["current_step_index"]]

    print(f"Session {session_id}, sending next action (Step {session['current_step_index'] + 1}/{session['max_steps']}): "
          f"Type '{next_action_detail.get('type', 'N/A')}'")
    return jsonify({
        "session_id": session_id,
        "action": next_action_detail,
        "message": f"Proceed with action for step {session['current_step_index'] + 1}."
    })


@app.route('/api/scripts/session/<session_id>/stop', methods=['POST'])
def stop_script_session_by_client(session_id):  # Đổi tên hàm
    if session_id in client_sessions:
        script_name = client_sessions[session_id]["script_name"]
        del client_sessions[session_id]
        print(
            f"Session {session_id} for script '{script_name}' actively stopped by client request.")
        return jsonify({"message": f"Session {session_id} for '{script_name}' stopped by your request."})
    else:
        print(
            f"Attempted to stop non-existent or already stopped session: {session_id}")
        return jsonify({"error": "Session not found or already stopped on server."}), 404


if __name__ == '__main__':
    initialize_server_directories()
    print(f"ADB Script Server starting...")
    print(f"Serving scripts from: {SCRIPTS_DIR}")
    print(f"Serving images from: {IMAGES_DIR}")
    print(
        f"Available scripts at startup: {[f.replace('.json', '') for f in os.listdir(SCRIPTS_DIR) if f.endswith('.json')]}")
    # Chạy trên 0.0.0.0 để có thể truy cập từ máy khác trong mạng
    # debug=True chỉ dùng khi phát triển, tắt nó khi triển khai thực tế
    app.run(host='0.0.0.0', port=5000, debug=True)
