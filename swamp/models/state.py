from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ZoneState:
    """State of a single SWAMP zone"""
    unit: int
    zone: int
    power: bool = False
    volume: int = 0
    source_id: int | None = None
    muted: bool = False
    source_received: bool = False  # True once we've received source data from device


@dataclass
class DeviceState:
    """Complete SWAMP device state"""
    zones: dict[tuple[int, int], ZoneState] = field(default_factory=dict)
    socket_connected: bool = False
    conn_accepted_sent: bool = False
    last_message_received: datetime | None = None
    client_address: str | None = None

    @property
    def connected(self) -> bool:
        """Device is considered connected if:
        - Socket is connected
        - CONN_ACCEPTED was sent
        - Message received in last 30 seconds
        """
        if not self.socket_connected or not self.conn_accepted_sent:
            return False

        if self.last_message_received is None:
            return False

        # Check if message received in last 30 seconds
        time_since_last = (datetime.now() - self.last_message_received).total_seconds()
        return time_since_last <= 30
