from swamp.protocol.base import ProtocolHandler


class SwampProtocol(ProtocolHandler):
    """SWAMP protocol implementation

    Message Format:
    All messages follow the format:
    - Byte 0: Message type
    - Bytes 1-2: Remaining length (total - 3) in big-endian
    - Bytes 3+: Payload

    Known Message Types:
    - 0x02: CONN_ACCEPTED (to device)
    - 0x05: JOIN (to/from device)
    - 0x0a: CLIENT_SIGNON (from device)
    - 0x0d: PING (from device)
    - 0x0e: PONG (to device)
    - 0x0f: WHOIS (to device)

    JOIN Message Format:
    - Bytes 0-2: Inner length (3 bytes big-endian) - size after these 3 bytes
    - Byte 3: Join type (0x03 = UPDATE)
    - Bytes 4+: Join payload
    """

    async def encode_route_command(self, unit: int, zone: int, source_id: int) -> bytes:
        """Convert routing command to wire format"""
        raise NotImplementedError("SWAMP protocol documentation needed")

    async def encode_volume_command(self, unit: int, zone: int, volume: int) -> bytes:
        """Convert volume command to wire format"""
        raise NotImplementedError("SWAMP protocol documentation needed")

    async def encode_power_command(self, unit: int, zone: int, power_on: bool) -> bytes:
        """Convert power command to wire format"""
        raise NotImplementedError("SWAMP protocol documentation needed")

    async def decode_message(self, data: bytes) -> dict | None:
        """Parse incoming message into structured data

        Format: [type (1), length (2), payload (length)]
        Length is remaining bytes (total - 3) in big-endian
        """
        if not data or len(data) < 3:
            return None

        message_type = data[0]
        remaining_length = int.from_bytes(data[1:3], 'big')

        # Verify message is complete
        expected_total = 3 + remaining_length
        if len(data) < expected_total:
            return None  # Incomplete message

        payload = data[3:3 + remaining_length]

        # Dispatch based on message type
        if message_type == 0x0d:
            return self._decode_ping(data, payload)
        elif message_type == 0x0a:
            return self._decode_client_signon(data, payload)
        elif message_type == 0x05:
            return self._decode_join(data, payload)
        # Add more message types here as we discover them

        return None

    def _decode_ping(self, data: bytes, payload: bytes) -> dict | None:
        """Decode PING message (0x0d)"""
        # PING: 0d 00 02 00 00
        # Type: 0x0d, Length: 2, Payload: 00 00
        if data == bytes([0x0d, 0x00, 0x02, 0x00, 0x00]):
            return {'type': 'ping'}
        return None

    def _decode_client_signon(self, data: bytes, payload: bytes) -> dict | None:
        """Decode CLIENT_SIGNON message (0x0a)

        Sent by device when it connects. We should respond with CONN_ACCEPTED.
        Protocol for payload contents is unknown.
        """
        # Example: 0a 00 0a 00 51 a3 42 40 02 00 00 00 00
        # Type: 0x0a, Length: 10 (0x00 0x0a), Payload: 00 51 a3 42 40 02 00 00 00 00
        return {
            'type': 'client_signon',
            'payload': payload.hex()
        }

    def _decode_join(self, data: bytes, payload: bytes) -> dict | None:
        """Decode JOIN message (0x05)

        JOIN payload format:
        - Bytes 0-2: Inner length (3 bytes big-endian)
        - Byte 3: Join type (0x03 = UPDATE)
        - Bytes 4+: Join data
        """
        if len(payload) < 4:
            return None

        inner_length = int.from_bytes(payload[0:3], 'big')
        join_type = payload[3]

        # Extract join data based on inner length
        join_data = payload[4:4 + inner_length - 1] if inner_length > 1 else b''

        join_type_name = 'update' if join_type == 0x03 else f'unknown_{join_type:02x}'

        return {
            'type': 'join',
            'join_type': join_type_name,
            'join_data': join_data.hex() if join_data else ''
        }

    async def encode_query_state(self, unit: int) -> bytes:
        """Request full state from device"""
        raise NotImplementedError("SWAMP protocol documentation needed")

    async def encode_whois(self) -> bytes:
        """Encode WHOIS request"""
        return bytes([0x0f, 0x00, 0x01, 0x02])

    async def encode_pong(self) -> bytes:
        """Encode PONG response

        Format: 0e 00 02 00 00
        Type: 0x0e, Length: 2, Payload: 00 00
        """
        return bytes([0x0e, 0x00, 0x02, 0x00, 0x00])

    async def encode_conn_accepted(self) -> bytes:
        """Encode CONN_ACCEPTED response

        Sent in response to CLIENT_SIGNON.
        Format: 02 00 04 00 00 00 03
        Type: 0x02, Length: 4, Payload: 00 00 00 03
        """
        return bytes([0x02, 0x00, 0x04, 0x00, 0x00, 0x00, 0x03])

    async def encode_join_update(self, payload_byte: int = 0x00) -> bytes:
        """Encode JOIN UPDATE message

        Sent 100ms after CONN_ACCEPTED.
        Format: 05 00 05 00 00 02 03 00
        Type: 0x05, Length: 5
        Payload:
          - Inner length: 00 00 02 (2 bytes remaining)
          - Join type: 03 (UPDATE)
          - Join data: 00 (configurable)
        """
        return bytes([
            0x05,        # Message type: JOIN
            0x00, 0x05,  # Remaining length: 5 bytes
            0x00, 0x00, 0x02,  # Inner length: 2 bytes
            0x03,        # Join type: UPDATE
            payload_byte # Join data
        ])
