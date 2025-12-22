from .base import ProtocolHandler


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
        """Convert routing command to wire format

        Uses SERIAL_BINARY JOIN to set source register (0x01)
        """
        return self._encode_serial_binary_register(unit, zone, 0x01, source_id)

    async def encode_volume_command(self, unit: int, zone: int, volume: int) -> bytes:
        """Convert volume command to wire format

        Uses SERIAL_BINARY JOIN to set volume register (0x02)
        Volume range: 0-100 maps to 0x0000-0xFFFF
        """
        # Convert volume from 0-100 to 0x0000-0xFFFF
        volume_value = int((volume / 100) * 0xFFFF)
        return self._encode_serial_binary_register(unit, zone, 0x02, volume_value)

    def _encode_serial_binary_register(self, unit: int, zone: int, register_id: int, value: int) -> bytes:
        """Encode SERIAL_BINARY JOIN message to set a register

        Format: 05 00 0e 00 00 0b 20 [unit] 08 20 [zone] 05 14 00 [reg] [val_hi] [val_lo]

        Args:
            unit: SWAMP unit number
            zone: SWAMP zone number
            register_id: 0x01 for source, 0x02 for volume
            value: Register value (2-byte integer)
        """
        # Ensure value fits in 2 bytes
        value = max(0, min(0xFFFF, value))
        value_hi = (value >> 8) & 0xFF
        value_lo = value & 0xFF

        return bytes([
            0x05,              # Message type: JOIN
            0x00, 0x0e,        # Remaining length: 14 bytes
            0x00, 0x00, 0x0b,  # Inner length: 11 bytes
            0x20,              # Join type: SERIAL_BINARY
            unit,              # Unit number
            0x08,              # Remaining length
            0x20,              # Join type repeated
            zone,              # Zone number
            0x05,              # Remaining length
            0x14,              # Register message type
            0x00,              # 0x00
            register_id,       # Register ID
            value_hi,          # Value high byte
            value_lo           # Value low byte
        ])

    async def encode_power_command(self, unit: int, zone: int, power_on: bool) -> bytes:
        """Convert power command to wire format

        Power on/off is handled by setting source register:
        - Power off: Set source to 0
        - Power on: Should set source to actual source (handled by controller)

        Note: This sets source to 0 for power off. For power on, use encode_route_command.
        """
        # Power off sets source to 0
        source_id = 0 if not power_on else 1  # Default to source 1 if on
        return self._encode_serial_binary_register(unit, zone, 0x01, source_id)

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
        elif message_type == 0x0e:
            return self._decode_pong(data, payload)
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

    def _decode_pong(self, data: bytes, payload: bytes) -> dict | None:
        """Decode PONG message (0x0e)"""
        # PONG: 0e 00 02 00 00
        # Type: 0x0e, Length: 2, Payload: 00 00
        if data == bytes([0x0e, 0x00, 0x02, 0x00, 0x00]):
            return {'type': 'pong'}
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
        - Byte 3: Join type (0x03 = UPDATE, 0x20 = SERIAL_BINARY)
        - Bytes 4+: Join data
        """
        if len(payload) < 4:
            return None

        inner_length = int.from_bytes(payload[0:3], 'big')
        join_type = payload[3]

        # Extract join data based on inner length
        join_data = payload[4:4 + inner_length - 1] if inner_length > 1 else b''

        if join_type == 0x03:
            return {
                'type': 'join',
                'join_type': 'update',
                'join_data': join_data.hex() if join_data else ''
            }
        elif join_type == 0x20:
            # SERIAL_BINARY - decode register data
            return self._decode_serial_binary(join_data)
        else:
            return {
                'type': 'join',
                'join_type': f'unknown_{join_type:02x}',
                'join_data': join_data.hex() if join_data else ''
            }

    def _decode_serial_binary(self, data: bytes) -> dict | None:
        """Decode SERIAL_BINARY JOIN payload (0x20)

        Format:
        - Byte 0: Unit number
        - Byte 1: Remaining message length
        - Byte 2: Join type repeated (0x20)
        - Byte 3: Zone number
        - Byte 4: Remaining message length
        - Byte 5: Register message type (0x14)
        - Byte 6: 0x00
        - Byte 7: Register ID (0x01=source, 0x02=volume)
        - Bytes 8-9: Data (2 bytes big-endian)
        """
        if len(data) < 10:
            return None

        unit = data[0]
        # data[1] is remaining length
        # data[2] should be 0x20 (join type repeated)
        zone = data[3]
        # data[4] is remaining length
        msg_type = data[5]
        # data[6] should be 0x00
        register_id = data[7]
        register_value = int.from_bytes(data[8:10], 'big')

        if msg_type != 0x14:
            # Unknown register message type
            return {
                'type': 'join',
                'join_type': 'serial_binary',
                'unit': unit,
                'zone': zone,
                'register_msg_type': f'unknown_{msg_type:02x}'
            }

        # Map register ID to name
        if register_id == 0x01:
            register_name = 'source'
        elif register_id == 0x02:
            register_name = 'volume'
            # Convert from 0-0xffff to 0-100
            register_value = int((register_value / 0xffff) * 100)
        else:
            register_name = f'unknown_{register_id:02x}'

        return {
            'type': 'join',
            'join_type': 'serial_binary',
            'unit': unit,
            'zone': zone,
            'register': register_name,
            'value': register_value
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

    def encode_join_digital_magic(self) -> tuple[bytes, bytes]:
        """Encode magic DIGITAL JOIN messages

        These must be sent once per connection before any SERIAL_BINARY messages.
        Returns a tuple of (message1, message2).

        Format: 05 00 06 00 00 03 00 [payload_hi] [payload_lo]
        - Message 1: 05 00 06 00 00 03 00 70 49
        - Message 2: 05 00 06 00 00 03 00 70 c9

        Purpose: Unknown initialization for SERIAL_BINARY communication
        """
        message1 = bytes([
            0x05,              # Message type: JOIN
            0x00, 0x06,        # Remaining length: 6 bytes
            0x00, 0x00, 0x03,  # Inner length: 3 bytes
            0x00,              # Join type: DIGITAL
            0x70, 0x49         # Magic payload
        ])

        message2 = bytes([
            0x05,              # Message type: JOIN
            0x00, 0x06,        # Remaining length: 6 bytes
            0x00, 0x00, 0x03,  # Inner length: 3 bytes
            0x00,              # Join type: DIGITAL
            0x70, 0xc9         # Magic payload
        ])

        return (message1, message2)
