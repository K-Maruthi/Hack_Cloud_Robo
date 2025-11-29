import asyncio
import websockets
import json
import random
import time
import math
import base64

# --- WORLD DEFINITION ---
WORLD_SIZE = 20.0 
# Objects: x, y, width, height, label, color
WORLD_MAP = [
    {"x": 10, "y": 10, "w": 2, "h": 2, "label": "PILLAR", "color": "#64748b"},
    {"x": 5, "y": 15, "w": 1, "h": 1, "label": "FORK-01", "color": "#f59e0b"},
    {"x": 15, "y": 5, "w": 1, "h": 1, "label": "STATION", "color": "#00f3ff"},
    {"x": 15, "y": 15, "w": 2, "h": 1, "label": "RACK-B", "color": "#ff0055"},
    {"x": 2, "y": 10, "w": 1, "h": 4, "label": "WALL-A", "color": "#334155"}
]

# --- ROBOT STATE ---
ROBOT = {
    "x": 2.0, "y": 2.0, "heading": 45.0,
    "vel_lin": 0.0, "vel_ang": 0.0,
    "mode": "AUTONOMOUS",
    "action": "IDLE", # IDLE, WALK, WAVE, CROUCH
    "target_idx": 0,
    "battery": 95.5,
    "camera_mode": "RGB"
}

# --- PHYSICS ENGINE ---
def update_physics(dt):
    if ROBOT["mode"] == "EMERGENCY_STOP":
        ROBOT["vel_lin"] = 0
        ROBOT["vel_ang"] = 0
        return

    # Move Robot
    rad = math.radians(ROBOT["heading"])
    ROBOT["x"] += math.cos(rad) * ROBOT["vel_lin"] * dt
    ROBOT["y"] += math.sin(rad) * ROBOT["vel_lin"] * dt
    ROBOT["heading"] = (ROBOT["heading"] + ROBOT["vel_ang"] * dt) % 360

    # Wall Clamping
    ROBOT["x"] = max(1, min(WORLD_SIZE-1, ROBOT["x"]))
    ROBOT["y"] = max(1, min(WORLD_SIZE-1, ROBOT["y"]))

    # Autonomous Logic
    if ROBOT["mode"] == "AUTONOMOUS":
        target = WORLD_MAP[ROBOT["target_idx"]]
        dx = target["x"] - ROBOT["x"]
        dy = target["y"] - ROBOT["y"]
        dist = math.sqrt(dx*dx + dy*dy)
        
        target_angle = math.degrees(math.atan2(dy, dx))
        angle_diff = (target_angle - ROBOT["heading"] + 180) % 360 - 180
        
        if dist < 1.5:
            ROBOT["vel_lin"] = 0
            ROBOT["action"] = "SCANNING"
            if random.random() < 0.02: 
                ROBOT["target_idx"] = (ROBOT["target_idx"] + 1) % len(WORLD_MAP)
                ROBOT["action"] = "WALK"
        else:
            ROBOT["vel_lin"] = 1.0
            ROBOT["vel_ang"] = angle_diff * 1.5
            ROBOT["action"] = "WALK"

# --- CAMERA GENERATOR (CO-RELATED RGB/DEPTH) ---
def generate_camera_frame():
    svg_objects = ""
    fov = 70
    
    # 1. Find visible objects
    visible_objects = []
    for obj in WORLD_MAP:
        dx = obj["x"] - ROBOT["x"]
        dy = obj["y"] - ROBOT["y"]
        dist = math.sqrt(dx*dx + dy*dy)
        angle_to_obj = math.degrees(math.atan2(dy, dx))
        rel_angle = (angle_to_obj - ROBOT["heading"] + 180) % 360 - 180
        
        if abs(rel_angle) < fov/2 and dist > 0.5:
            visible_objects.append((dist, rel_angle, obj))
            
    visible_objects.sort(key=lambda x: x[0], reverse=True) # Painter's Algorithm
    
    # 2. Render Objects
    for dist, angle, obj in visible_objects:
        size = 800 / dist
        x_screen = 320 + (angle / (fov/2)) * 320 - (size/2)
        y_screen = 180 - (size/2)
        
        if ROBOT["camera_mode"] == "RGB":
            # Wireframe Look
            stroke = obj["color"]
            fill = "none"
            opacity = 1.0
            text_fill = "white"
        else: 
            # Depth Heatmap Look (Closer = Hotter/Brighter)
            # Map distance 1m->20m to Hue
            heat_val = max(0, 255 - (dist * 12))
            fill = f"rgb({heat_val}, 0, {255-heat_val})"
            stroke = "none"
            opacity = 0.8
            text_fill = "none" # No text in raw depth mode
            
        svg_objects += f"""
            <rect x="{x_screen}" y="{y_screen}" width="{size}" height="{size}" 
                  stroke="{stroke}" stroke-width="2" fill="{fill}" opacity="{opacity}"/>
            <text x="{x_screen + size/2}" y="{y_screen - 10}" text-anchor="middle" fill="{text_fill}" font-family="monospace" font-size="10">{obj['label']}</text>
        """

    bg = "#020617" if ROBOT["camera_mode"] == "RGB" else "#0a001a"
    
    svg = f"""
    <svg width="640" height="360" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="{bg}"/>
        <!-- Grid Floor -->
        <g stroke="#3b82f6" stroke-width="1" opacity="0.3">
            <line x1="0" y1="220" x2="640" y2="220"/>
            <line x1="0" y1="360" x2="640" y2="360"/>
            <line x1="320" y1="180" x2="-300" y2="360"/>
            <line x1="320" y1="180" x2="940" y2="360"/>
        </g>
        {svg_objects}
        <text x="20" y="30" fill="#3b82f6" font-family="monospace">SENSOR: {ROBOT['camera_mode']}</text>
    </svg>
    """
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode('utf-8')).decode('utf-8')

# --- SENSORS ---
def get_lidar_scan():
    # Simple Raycast approximation
    points = []
    for angle in range(0, 360, 4):
        rad = math.radians(ROBOT["heading"] + angle)
        dist = 20.0 # Max range
        # Check against objects
        for obj in WORLD_MAP:
            d_obj = math.sqrt((obj["x"]-ROBOT["x"])**2 + (obj["y"]-ROBOT["y"])**2)
            # Simple angle check
            obj_angle = math.degrees(math.atan2(obj["y"]-ROBOT["y"], obj["x"]-ROBOT["x"]))
            diff = abs((obj_angle - (ROBOT["heading"]+angle) + 180) % 360 - 180)
            if diff < 5 and d_obj < dist:
                dist = d_obj
        points.append(dist)
    return points

async def command_listener(ws):
    async for message in ws:
        try:
            data = json.loads(message)
            cmd = data.get("action")
            print(f"[CMD] {cmd}")
            
            if cmd == "TOGGLE_MODE":
                ROBOT["mode"] = "MANUAL" if ROBOT["mode"] == "AUTONOMOUS" else "AUTONOMOUS"
            elif cmd == "STOP": ROBOT["mode"] = "EMERGENCY_STOP"
            elif cmd == "START": ROBOT["mode"] = "AUTONOMOUS"
            elif cmd == "CAM_SWITCH": ROBOT["camera_mode"] = "DEPTH" if ROBOT["camera_mode"] == "RGB" else "RGB"
            
            # Manual Actions
            if ROBOT["mode"] == "MANUAL":
                if cmd == "MOVE_FORWARD": ROBOT["vel_lin"] = 1.5
                elif cmd == "MOVE_BACKWARD": ROBOT["vel_lin"] = -1.0
                elif cmd == "TURN_LEFT": ROBOT["vel_ang"] = -45
                elif cmd == "TURN_RIGHT": ROBOT["vel_ang"] = 45
                elif cmd == "HALT_MOVE": 
                    ROBOT["vel_lin"] = 0
                    ROBOT["vel_ang"] = 0
                elif cmd in ["ACTION_WAVE", "ACTION_CROUCH", "ACTION_GRAB"]:
                    ROBOT["action"] = cmd.replace("ACTION_", "")
        except: pass

async def stream_data():
    uri_t = "ws://127.0.0.1:8001/ws/telemetry"
    uri_v = "ws://127.0.0.1:8001/ws/video"
    uri_k = "ws://127.0.0.1:8001/ws/kinematics"
    
    async with websockets.connect(uri_t) as ws_t, websockets.connect(uri_v) as ws_v, websockets.connect(uri_k) as ws_k:
        asyncio.create_task(command_listener(ws_t))
        print("🚀 UNIFIED SIMULATOR ONLINE")
        
        while True:
            dt = 0.1
            update_physics(dt)
            t = time.time()
            
            # --- 1. FULL TELEMETRY (Hardware + Power) ---
            ROBOT["battery"] -= 0.001
            cells = [round(4.0 + random.uniform(-0.02, 0.02), 2) for _ in range(6)]
            force = [round(random.uniform(0, 10), 1) for _ in range(10)]
            tactile = [1 if random.random() > 0.9 else 0 for _ in range(20)]
            
            telemetry = {
                "message_type": "telemetry",
                "system": {"cpu_percent": 30 + abs(ROBOT["vel_lin"])*10, "gpu_tops": 45.2, "memory_gb": 8.15, "network_signal_dbm": -48},
                "power": {
                    "battery_percent": round(ROBOT["battery"], 1),
                    "voltage_v": 24.1, "current_a": 12.5, "power_w": 300, "runtime_min": 140,
                    "cell_voltages": cells
                },
                "sensors": {
                    "lidar_scan": get_lidar_scan(),
                    "force": force,
                    "tactile": tactile,
                    "motor_temps": [42.0]*32
                },
                "imu": {
                    "accel": [0.0, 0.0, 9.81],
                    "gyro": [0.0, 0.0, ROBOT["vel_ang"]/10],
                    "mag": [14, 35, -10]
                }
            }
            
            # --- 2. VISION ---
            vision = {
                "message_type": "vision",
                "current_zone": ROBOT["mode"],
                "robot_pose": {"x": ROBOT["x"], "y": ROBOT["y"], "heading": ROBOT["heading"]},
                "detected_objects": [] # Populated dynamically
            }
            
            # --- 3. KINEMATICS (Action Based) ---
            # 32 Joints
            joints = [0.0] * 32
            if ROBOT["action"] == "WALK":
                joints = [round(math.sin(t+i)*30, 1) for i in range(32)]
            elif ROBOT["action"] == "WAVE":
                joints[2] = round(math.sin(t*5)*60, 1) # Elbow
            elif ROBOT["action"] == "CROUCH":
                joints = [45.0 if i > 10 else 0 for i in range(32)]
                
            kinematics = {
                "message_type": "kinematics",
                "h3_mobility": {"joint_angles": joints}
            }
            
            # --- 4. CAMERA ---
            camera = {"message_type": "camera_feed", "frame": generate_camera_frame()}

            await ws_t.send(json.dumps(telemetry))
            await ws_t.send(json.dumps(vision))
            await ws_k.send(json.dumps(kinematics))
            await ws_v.send(json.dumps(camera))
            
            await asyncio.sleep(dt)

if __name__ == "__main__":
    asyncio.run(stream_data())