from fastapi import WebSocket
from typing import List, Dict

class ConnectionManager:
    def __init__(self):
        self.dashboard_connections: List[WebSocket] = []
        # Store robot connections: { "humanoid_001": WebSocket }
        self.robot_connections: Dict[str, WebSocket] = {}

    # --- ROBOT HANDLING ---
    async def connect_robot(self, websocket: WebSocket, robot_id: str = "humanoid_001"):
        await websocket.accept()
        self.robot_connections[robot_id] = websocket
        print(f"[SYSTEM] ROBOT {robot_id} CONNECTED via Command Link.")

    def disconnect_robot(self, robot_id: str):
        if robot_id in self.robot_connections:
            del self.robot_connections[robot_id]
            print(f"[SYSTEM] ROBOT {robot_id} DISCONNECTED.")

    async def send_command_to_robot(self, robot_id: str, command: dict):
        if robot_id in self.robot_connections:
            await self.robot_connections[robot_id].send_json(command)
            return True
        return False

    # --- DASHBOARD HANDLING ---
    async def connect_dashboard(self, websocket: WebSocket):
        await websocket.accept()
        self.dashboard_connections.append(websocket)

    def disconnect_dashboard(self, websocket: WebSocket):
        if websocket in self.dashboard_connections:
            self.dashboard_connections.remove(websocket)

    async def broadcast_to_dashboards(self, message: str, channel: str):
        for connection in self.dashboard_connections:
            try:
                await connection.send_text(message)
            except:
                self.disconnect_dashboard(connection)

manager = ConnectionManager()