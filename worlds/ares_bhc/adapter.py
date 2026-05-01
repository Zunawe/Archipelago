from __future__ import annotations

import asyncio
import base64
import enum
import json
from typing import Any, TypeAlias


Request: TypeAlias = dict[str, Any]
Response: TypeAlias = dict[str, Any]

_DOMAIN_OFFSETS = {
    "RDRAM":      0xA000_0000,
    "ROM":        0xB000_0000,
    "System Bus": 0x0000_0000,
}
_EFFECTFUL_REQUESTS = {"WRITE", "LOCK", "UNLOCK"}


def gdb_packet(command: str) -> str:
    return f"+${command}#00"  # ares discards the checksum


def gdb_read(address: int, domain: str, size: int) -> str:
    offset_address = address + _DOMAIN_OFFSETS[domain]
    return gdb_packet(f"m{offset_address:x},{size:x}")


def gdb_write(address: int, domain: str, value: bytes) -> str:
    offset_address = address + _DOMAIN_OFFSETS[domain]
    return gdb_packet(f"M{offset_address:x},{len(value):x}:{value.hex()}")


def gdb_set_vi_origin_watchpoint() -> str:
    return gdb_packet("Z2,a4400004,4")


def gdb_unset_vi_origin_watchpoint() -> str:
    return gdb_packet("z2,a4400004,4")


def gdb_halt() -> str:
    return gdb_packet("?")


def gdb_continue() -> str:
    return gdb_packet("c")


def preprocess_request(request: Request) -> None:
    if request["type"] == "GUARD":
        request["expected_data"] = base64.b64decode(request["expected_data"])
        if len(request["expected_data"]) not in (1, 2, 4, 8):
            raise Exception("Can only safely read 1, 2, 4, or 8 bytes at a time on ares")
    elif request["type"] == "READ":
        request["expected_data"] = base64.b64decode(request["expected_data"])
        if request["size"] not in (1, 2, 4, 8):
            raise Exception("Can only safely read 1, 2, 4, or 8 bytes at a time on ares")
    elif request["type"] == "WRITE":
        request["value"] = base64.b64decode(request["value"])
        if len(request["value"]) not in (1, 2, 4, 8):
            raise Exception("Can only safely write 1, 2, 4, or 8 bytes at a time on ares")


class AresConnection:
    _reader: asyncio.StreamReader
    _writer: asyncio.StreamWriter
    _connection_closed: bool
    lock: asyncio.Lock

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._connection_closed = False
        self.lock = asyncio.Lock()

    async def send_and_receive(self, message: str, include_halt = False) -> str:
        async with self.lock:
            try:
                if include_halt:
                    # Send watchpoint set on V_ORIGIN, which is primarily a
                    # reliable anchor point for consistency per frame.
                    # Then wait for the game to halt.
                    # Then prepend a command to remove the watchpoint.
                    self._writer.write(gdb_set_vi_origin_watchpoint().encode("ascii"))
                    await asyncio.wait_for(self._writer.drain(), 5)
                    watchpoint_ack = await asyncio.wait_for(self._reader.read(30), 5)
                    assert watchpoint_ack == b"+$OK#9a+$T05watch:a4400004;#02"
                    message = gdb_unset_vi_origin_watchpoint() + message

                self._writer.write(message.encode("ascii"))
                await asyncio.wait_for(self._writer.drain(), 5)
                res = await asyncio.wait_for(self._reader.read(4096), 5)

                if res == b"":
                    self._writer.close()
                    self._connection_closed = True
                    raise Exception("Connection to ares closed")

                ret = res.decode("ascii")
                if include_halt:
                    # Remove the acknowledgement from unsetting the watchpoint
                    assert ret.startswith("+$OK#9a")
                    ret = ret[7:]
                return ret
            except asyncio.TimeoutError as exc:
                self._writer.close()
                self._connection_closed = True
                raise Exception("Connection to ares timed out") from exc
            except ConnectionResetError as exc:
                self._writer.close()
                self._connection_closed = True
                raise Exception("Connection to ares reset") from exc

    @classmethod
    async def connect(cls, port: int) -> AresConnection | None:
        try:
            reader, writer = await asyncio.open_connection("localhost", port)
            return cls(reader, writer)
        except (TimeoutError, ConnectionRefusedError):
            pass
        return None


class AresContext:
    _connection: AresConnection | None
    _locked_state: bool

    def __init__(self) -> None:
        self._locked_state = False
    
    async def connect(self) -> None:
        self._connection = await AresConnection.connect(9123)

    async def process_requests(self, requests: list[Request]) -> list[Response]:
        assert self._connection is not None

        for request in requests:
            preprocess_request(request)

        request_data = []

        packets = []
        for request in requests:
            packet = ""
            if request["type"] == "GUARD":
                packet = gdb_read(request["address"], request["domain"], len(request["expected_data"]))
            elif request["type"] == "READ":
                packet = gdb_read(request["address"], request["domain"], request["size"])
            elif request["type"] == "WRITE":
                packet = gdb_write(request["address"], request["domain"], request["value"])
            packets.append(packet)

        failed_guard_index = None
        bounds = [0, 0]
        while bounds[1] < len(requests):
            in_guarded_state = False
            send_halt = False

            for i in range(bounds[0], len(requests)):
                if requests[i]["type"] == "GUARD":
                    in_guarded_state = True
                elif in_guarded_state and requests[i]["type"] in _EFFECTFUL_REQUESTS:
                    break
                bounds[1] += 1

            message = "".join(packets[bounds[0]:bounds[1]])

            num_locks = sum(
                -1 if request["type"] == "UNLOCK" else (1 if request["type"] == "LOCK" else 0)
                for request in requests[bounds[0]:bounds[1]]
            )
            # TODO: Avoid sending lock/continue for request chains of length 1? Breaks implicit lock/unlock handling
            if not self._locked_state:
                if bounds[0] == 0:
                    send_halt = True  # Emulator isn't currently paused, halt for request chain
                if bounds[1] == len(requests):
                    message += gdb_continue()  # Emulator is supposed to be running after request chain
                if num_locks > 0:
                    self._locked_state = True  # Requests are triggering a lock
            else:
                if num_locks < 0: 
                    self._locked_state = False  # Requests are triggering an unlock

            raw_responses = iter((await self._connection.send_and_receive(message, send_halt)).split("+"))
            next(raw_responses)  # Empty string left of the first '+'

            for i, request in enumerate(requests[bounds[0]:bounds[1]]):
                data = None
                if request["type"] == "WRITE":
                    acknowledge = next(raw_responses)
                    assert acknowledge == "$OK#9a"
                elif request["type"] in ("GUARD", "READ"):
                    data_str = next(raw_responses)
                    data = bytes.fromhex(data_str[1:data_str.index("#")])
                    if failed_guard_index is None and request["type"] == "GUARD" and data != request["expected_data"]:
                        failed_guard_index = bounds[0] + i
                request_data.append(data)

            if failed_guard_index is not None:
                break
            bounds[0] = bounds[1]

        responses = []
        for i, request in enumerate(requests):
            if failed_guard_index is not None and i > failed_guard_index:
                responses.append(responses[-1])
                continue

            if request["type"] == "PING":
                responses.append({
                    "type": "PONG",
                })
            elif request["type"] == "SYSTEM":
                responses.append({
                    "type": "SYSTEM_RESPONSE",
                    "value": "N64",
                })
            elif request["type"] == "PREFERRED_CORES":
                responses.append({
                    "type": "PREFERRED_CORES_RESPONSE",
                    "value": {},
                })
            elif request["type"] == "HASH":
                # TODO: Maybe read ROM header
                responses.append({
                    "type": "HASH_RESPONSE",
                    "value": "1",
                })
            elif request["type"] == "MEMORY_SIZE":
                # TODO: Implement/hardcode
                responses.append({
                    "type": "MEMORY_SIZE_RESPONSE",
                    "value": "1",
                })
            elif request["type"] == "GUARD":
                responses.append({
                    "type": "GUARD_RESPONSE",
                    "value": request_data[i] == request["expected_data"],
                    "address": request["address"],
                })
            elif request["type"] == "LOCK":
                responses.append({
                    "type": "LOCKED",
                })
            elif request["type"] == "UNLOCK":
                responses.append({
                    "type": "UNLOCKED",
                })
            elif request["type"] == "READ":
                responses.append({
                    "type": "READ_RESPONSE",
                    "value": base64.b64encode(request_data[i]).decode("ascii"),
                })
            elif request["type"] == "WRITE":
                responses.append({
                    "type": "WRITE_RESPONSE",
                })
            elif request["type"] == "DISPLAY_MESSAGE":
                responses.append({
                    "type": "DISPLAY_MESSAGE_RESPONSE",
                })
            elif request["type"] == "SET_MESSAGE_INTERVAL":
                responses.append({
                    "type": "SET_MESSAGE_INTERVAL_RESPONSE",
                })
        return responses


async def main():
    ares_ctx = AresContext()
    await ares_ctx.connect()

    async def on_client_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                try:
                    req = await asyncio.wait_for(reader.readline(), 5)
                except asyncio.TimeoutError:
                    break

                if req == b"":
                    break

                req_str = req.decode("utf-8")
                if req_str == "VERSION\n":
                    writer.write("1\n".encode("utf-8"))
                    await asyncio.wait_for(writer.drain(), 5)
                    continue

                responses = await ares_ctx.process_requests(json.loads(req_str))
                writer.write(json.dumps(responses).encode("utf-8") + b"\n")
                await asyncio.wait_for(writer.drain(), 5)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(on_client_connect, "localhost", 43055)
    async with server:
        await server.serve_forever()


asyncio.run(main())
