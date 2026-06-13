"""
WebSocket broadcaster — pushes context updates to all connected members.
Call broadcast() after every agent action so all clients stay in sync.
"""
import asyncio
import json
from fastapi import WebSocket


class Broadcaster:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, member: str, ws: WebSocket):
        await ws.accept()
        self._connections[member] = ws

    def disconnect(self, member: str):
        self._connections.pop(member, None)

    async def broadcast(self, event: str, data: dict):
        message = json.dumps({"event": event, "data": data})
        dead = []
        for member, ws in self._connections.items():
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(member)
        for m in dead:
            self.disconnect(m)

    async def send_to(self, member: str, event: str, data: dict):
        ws = self._connections.get(member)
        if ws:
            try:
                await ws.send_text(json.dumps({"event": event, "data": data}))
            except Exception:
                self.disconnect(member)
