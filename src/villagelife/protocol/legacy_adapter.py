"""Adapter boundary for ORIGINAL APK RPCs.

A compatible response implementation has NOT been ported yet. The legacy
0.2.6 source is retained under legacy_reference/ for controlled transfer.
"""
from typing import Protocol
from villagelife.core.errors import NotImplementedRule


class LegacyRpcHandler(Protocol):
    def process(self, path: str, request: dict) -> dict: ...


class MissingLegacyHandler:
    def process(self, path: str, request: dict) -> dict:
        raise NotImplementedRule('Legacy client RPC is not yet ported: '+path)


class LegacyProtocolAdapter:
    def __init__(self, handler: LegacyRpcHandler):
        self.handler = handler

    def handle(self, path: str, body: bytes) -> bytes:
        from .legacy_codec import decode, encode
        document, mode = decode(body)
        answer = self.handler.process(path, document)
        return encode(answer, compressed=(mode == 'zlib-xor'))
