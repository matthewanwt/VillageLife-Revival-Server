"""Historical client wire codec, isolated from gameplay and storage modules."""
import json
import zlib

KEY = b'PlaydemicLTD'
MAX_DECODED = 8 * 1024 * 1024


def _xor(data: bytes) -> bytes:
    return bytes(value ^ KEY[i % len(KEY)] for i, value in enumerate(data))


def decode(data: bytes) -> tuple[dict, str]:
    if len(data) > MAX_DECODED:
        raise ValueError('Message too large')
    mode = 'plain'
    if not data.startswith((b'q=', b'{', b'[')):
        dec = zlib.decompressobj()
        data = dec.decompress(_xor(data), MAX_DECODED + 1)
        if not dec.eof or len(data) > MAX_DECODED or dec.unused_data:
            raise ValueError('Invalid legacy compressed message')
        mode = 'zlib-xor'
    if data.startswith(b'q='):
        data = data[2:]
    result = json.loads(data.decode('utf-8'))
    if not isinstance(result, dict):
        raise ValueError('Request must be JSON object')
    return result, mode


def encode(data: dict, *, compressed: bool) -> bytes:
    raw = json.dumps(data, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return _xor(zlib.compress(raw)) if compressed else raw
