"""
Client WebSocket vers le serveur Orion (endpoint /ws/{device_id}).

Le service voix se connecte exactement comme l'UI navigateur ou agent.py
en mode controller : il envoie {"type": "message", "content": ...} et reçoit
des {"type": "response"|"tool_action"|"info"|"error"|"connected"|"pong"}.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

try:
    import websockets
    from websockets.exceptions import ConnectionClosed
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "websockets n'est pas installé. Installe avec :\n"
        "    pip install -r requirements-voice.txt"
    ) from exc


class OrionClient:
    """Client async pour parler au serveur Orion."""

    def __init__(self, server_url: str, device_id: str, token: str):
        # server_url accepté en ws://host:port (sans /ws/...)
        base = server_url.rstrip("/")
        self.url = f"{base}/ws/{device_id}?token={token}"
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self):
        print(f"[orion] Connexion à {self.url}")
        self._ws = await websockets.connect(
            self.url, ping_interval=20, ping_timeout=20, max_size=8 * 1024 * 1024
        )
        # Le serveur envoie un message {"type": "connected", ...} en welcome
        welcome_raw = await self._ws.recv()
        try:
            welcome = json.loads(welcome_raw)
            print(f"[orion] {welcome.get('message', 'Connecté')}")
        except json.JSONDecodeError:
            pass

    async def close(self):
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_message(self, content: str):
        if self._ws is None:
            raise RuntimeError("Client non connecté")
        await self._ws.send(json.dumps({"type": "message", "content": content}))

    async def send_clear_history(self):
        if self._ws is None:
            return
        await self._ws.send(json.dumps({"type": "clear_history"}))

    async def send_voice_state(self, state: str):
        """Notifie le serveur de l'état du pipeline voix (broadcast aux UI)."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "voice_state", "state": state}))
        except Exception:
            # Best-effort : on ne casse pas le pipeline si l'envoi échoue
            pass

    async def send_unlock_request(self):
        """Demande au serveur de déverrouiller les UI navigateur connectées."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "unlock_request"}))
        except Exception:
            pass

    async def receive_response(
        self, timeout: float | None = 120.0
    ) -> AsyncIterator[dict]:
        """Itère sur les messages du serveur jusqu'à recevoir 'response' ou 'error'.

        Yield chaque message reçu (tool_action, info, etc.) puis termine après
        le message final de type 'response' ou 'error'.
        """
        if self._ws is None:
            raise RuntimeError("Client non connecté")

        end_at = None
        if timeout is not None:
            loop = asyncio.get_running_loop()
            end_at = loop.time() + timeout

        while True:
            remaining = None
            if end_at is not None:
                loop = asyncio.get_running_loop()
                remaining = max(0.1, end_at - loop.time())

            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                yield {"type": "error", "content": "Timeout serveur Orion"}
                return
            except ConnectionClosed as exc:
                yield {"type": "error", "content": f"Connexion fermée : {exc}"}
                return

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            yield data
            if data.get("type") in ("response", "error"):
                return
