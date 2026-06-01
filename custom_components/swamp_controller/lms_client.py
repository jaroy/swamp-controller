"""Lyrion Music Server (LMS) JSON-RPC client.

The SWAMP zones are exposed to Music Assistant as Home Assistant media players.
MA streams audio to those entities via ``media_player.play_media`` with an HTTP
stream URL. The actual rendering is done by a squeezelite player wired to a SWAMP
analog input; that squeezelite is driven by a *real* Lyrion Music Server (not MA's
emulated LMS, which rejects URL injection). This client is the thin control surface
we use to make a given squeezelite player render the URL MA handed us and to read
its playback state back so the zone entity can mirror it.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class LmsClient:
    """Minimal async client for the LMS JSON-RPC (``/jsonrpc.js``) endpoint."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int = 9000) -> None:
        self._session = session
        self._url = f"http://{host}:{port}/jsonrpc.js"

    async def _request(self, player_id: str, command: list[Any]) -> dict[str, Any]:
        """Send a ``slim.request`` and return the ``result`` dict (or {})."""
        payload = {
            "id": 1,
            "method": "slim.request",
            "params": [player_id, command],
        }
        async with self._session.post(self._url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
        if "error" in data:
            raise LmsError(f"LMS rejected {command!r}: {data['error']}")
        result = data.get("result")
        return result if isinstance(result, dict) else {}

    # --- transport / playback control -------------------------------------

    async def play_url(self, player_id: str, url: str) -> None:
        """Replace the playlist with ``url`` and start playing it."""
        await self._request(player_id, ["playlist", "play", url])

    async def pause(self, player_id: str) -> None:
        await self._request(player_id, ["pause", "1"])

    async def unpause(self, player_id: str) -> None:
        await self._request(player_id, ["pause", "0"])

    async def stop(self, player_id: str) -> None:
        await self._request(player_id, ["stop"])

    async def next_track(self, player_id: str) -> None:
        await self._request(player_id, ["playlist", "index", "+1"])

    async def previous_track(self, player_id: str) -> None:
        await self._request(player_id, ["playlist", "index", "-1"])

    async def seek(self, player_id: str, position: float) -> None:
        await self._request(player_id, ["time", position])

    async def set_volume(self, player_id: str, volume_pct: int) -> None:
        """Set the player's software volume (0-100)."""
        await self._request(player_id, ["mixer", "volume", str(int(volume_pct))])

    async def power(self, player_id: str, on: bool) -> None:
        await self._request(player_id, ["power", "1" if on else "0"])

    # --- state ------------------------------------------------------------

    async def status(self, player_id: str) -> dict[str, Any]:
        """Return raw status for the player (mode, time, duration, title, ...)."""
        return await self._request(
            player_id, ["status", "-", 1, "tags:abcdltuKN"]
        )

    async def is_connected(self, player_id: str) -> bool:
        """Whether the given squeezelite player is currently connected to LMS."""
        result = await self._request("", ["players", "0", "100"])
        for player in result.get("players_loop", []):
            if player.get("playerid", "").lower() == player_id.lower():
                return bool(player.get("connected"))
        return False


class LmsError(Exception):
    """Raised when LMS returns an error for a command."""
