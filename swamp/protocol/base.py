from abc import ABC, abstractmethod


class ProtocolHandler(ABC):
    """Abstract base for SWAMP protocol implementations"""

    @abstractmethod
    async def encode_route_command(self, unit: int, zone: int, source_id: int) -> bytes:
        """Convert routing command to wire format"""
        pass

    @abstractmethod
    async def encode_volume_command(self, unit: int, zone: int, volume: int) -> bytes:
        """Convert volume command to wire format"""
        pass

    @abstractmethod
    async def encode_power_command(self, unit: int, zone: int, power_on: bool) -> bytes:
        """Convert power command to wire format"""
        pass

    @abstractmethod
    async def decode_message(self, data: bytes) -> dict | None:
        """Parse incoming message into structured data"""
        pass

    @abstractmethod
    async def encode_query_state(self, unit: int) -> bytes:
        """Request full state from device"""
        pass

    @abstractmethod
    async def encode_whois(self) -> bytes:
        """Encode WHOIS request"""
        pass

    @abstractmethod
    async def encode_pong(self) -> bytes:
        """Encode PONG response"""
        pass

    @abstractmethod
    async def encode_conn_accepted(self) -> bytes:
        """Encode CONN_ACCEPTED response"""
        pass
