import asyncio
import json
from contextlib import suppress

from anyio import CancelScope
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .errors import APIError, INVALID_LINK

router = APIRouter()


async def message(socket: WebSocket) -> dict:
    frame = await socket.receive()
    if frame["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(frame.get("code", 1000))
    try:
        value = json.loads(frame.get("text", ""))
    except (ValueError, TypeError):
        value = None
    if not isinstance(value, dict):
        raise APIError(400, "invalid_message", "Expected a JSON message object.")
    return value


async def send_events(socket: WebSocket, queue: asyncio.Queue):
    while True:
        await asyncio.wait_for(socket.send_json(await queue.get()), timeout=5)


async def receive_pings(socket: WebSocket, queue: asyncio.Queue):
    while True:
        try:
            value = await asyncio.wait_for(message(socket), socket.app.state.heartbeat_timeout)
        except TimeoutError:
            raise APIError(400, "invalid_message", "Heartbeat timed out.") from None
        if value != {"type": "ping"}:
            raise APIError(400, "invalid_message", "Expected a ping message.")
        queue.put_nowait({"type": "pong"})


async def fail(socket: WebSocket, code: str, text: str, close_code: int):
    with suppress(WebSocketDisconnect, RuntimeError, OSError, TimeoutError):
        await asyncio.wait_for(socket.send_json({"type": "error", "code": code, "message": text}), 5)
        await socket.close(code=close_code)


@router.websocket("/sessions/{sessionId}/ws")
async def connect(socket: WebSocket, sessionId: str):
    if socket.headers.get("origin") not in socket.app.state.frontend_origins:
        await socket.close(code=1008)
        return
    await socket.accept()
    session = queue = role = None
    tasks = []
    try:
        try:
            value = await asyncio.wait_for(message(socket), socket.app.state.auth_timeout)
        except TimeoutError:
            raise APIError(404, "invalid_link", INVALID_LINK) from None
        if (set(value) != {"type", "token"} or value["type"] != "authenticate"
                or not isinstance(value["token"], str) or not value["token"]):
            raise APIError(400, "invalid_message", "Expected an authentication message.")
        session, role = socket.app.state.store.authorize(sessionId, value["token"])
        queue = await session.subscribe(role)
        tasks = [asyncio.create_task(send_events(socket, queue)),
                 asyncio.create_task(receive_pings(socket, queue))]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in tasks:
            if task not in done:
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task not in done), return_exceptions=True)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except APIError as exc:
        await fail(socket, exc.code, exc.message, 1008)
    except Exception:
        # Never echo exception details, authentication messages, or tokens.
        await fail(socket, "internal_error", "Could not complete the request. Please try again.", 1011)
    finally:
        # Finish local cleanup even when the ASGI connection scope is cancelled.
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if queue is not None:
                await session.unsubscribe(role, queue)
