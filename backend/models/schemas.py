from pydantic import BaseModel
from typing import Dict, Any, Optional

class TelemetryData(BaseModel):
    robot_id: str
    timestamp: float
    type: str  # 'high_freq' or 'low_freq'
    payload: Dict[str, Any]
