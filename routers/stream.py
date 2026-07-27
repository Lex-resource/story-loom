import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from routers._common import is_valid_project_id
from services.access_control import websocket_access_allowed
from services.stream_constants import STREAM_SOURCE_SYSTEM
from services.stream_manager import stream_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    if not websocket_access_allowed(websocket):
        await websocket.close(code=1008, reason="Remote access is disabled")
        return
    if not is_valid_project_id(project_id):
        await websocket.close(code=1008, reason="Invalid project_id")
        return

    await websocket.accept()
    stream_manager.register_connection(project_id, websocket)

    # Broadcast connection success log
    await stream_manager.broadcast(
        project_id,
        "log",
        {"source": STREAM_SOURCE_SYSTEM, "message": "已连接到创作现场双向控制台。"}
    )

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            msg_type = data.get("type")

            if msg_type == "pause":
                await websocket.send_json({"type": "warning", "message": "请使用 REST 暂停接口。"})
            elif msg_type == "resume":
                await websocket.send_json({"type": "warning", "message": "请使用 REST 恢复接口。"})
            elif msg_type == "insert_prompt":
                await websocket.send_json({"type": "warning", "message": "请使用 REST 人工指令接口。"})
            elif msg_type == "change_model":
                await websocket.send_json({"type": "error", "message": "模型切换仅允许通过设置接口。"})

    except WebSocketDisconnect:
        logger.info("websocket_disconnected project_id=%s", project_id)
    except Exception:
        logger.exception("websocket_failed project_id=%s", project_id)
    finally:
        stream_manager.unregister_connection(project_id, websocket)
