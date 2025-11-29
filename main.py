from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from backend.core.websocket_manager import manager

app = FastAPI(title="S4 Robot System")

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# --- DATA MODELS ---
class RobotCommand(BaseModel):
    action: str  # "STOP", "MODE_AUTO", "MODE_MANUAL", "REBOOT"

# --- ROUTES ---
@app.get("/")
async def landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/dashboard/{robot_id}")
async def dashboard_page(request: Request, robot_id: str):
    return templates.TemplateResponse("dashboard.html", {"request": request, "robot_id": robot_id})

@app.post("/api/command/{robot_id}")
async def send_command(robot_id: str, cmd: RobotCommand):
    """API Endpoint called by Frontend Buttons"""
    success = await manager.send_command_to_robot(robot_id, {"command": cmd.action})
    if not success:
        raise HTTPException(status_code=404, detail="Robot not connected")
    return {"status": "sent", "action": cmd.action}

# --- WEBSOCKETS ---

# 1. KINEMATICS
@app.websocket("/ws/kinematics")
async def kinematics_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast_to_dashboards(data, "kinematics")
    except WebSocketDisconnect: pass

# 2. VIDEO
@app.websocket("/ws/video")
async def video_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast_to_dashboards(data, "video")
    except WebSocketDisconnect: pass

# 3. TELEMETRY (This is also our Command Channel)
@app.websocket("/ws/telemetry")
async def telemetry_endpoint(websocket: WebSocket):
    # Register the robot so we can talk back to it
    await manager.connect_robot(websocket, "humanoid_001")
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast_to_dashboards(data, "telemetry")
    except WebSocketDisconnect:
        manager.disconnect_robot("humanoid_001")

# 4. DASHBOARD
@app.websocket("/ws/dashboard")
async def dashboard_endpoint(websocket: WebSocket):
    await manager.connect_dashboard(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_dashboard(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)