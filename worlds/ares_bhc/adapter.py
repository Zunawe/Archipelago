from __future__ import annotations

import asyncio
import base64
import enum
import json
from typing import Any


class ConnectionStatus(enum.IntEnum):
    NOT_CONNECTED = 1
    TENTATIVE = 2
    CONNECTED = 3


class AresContext:
    streams: tuple[asyncio.StreamReader, asyncio.StreamWriter] | None
    connection_status: ConnectionStatus
    lock: asyncio.Lock

    def __init__(self) -> None:
        self.streams = None
        self.connection_status = ConnectionStatus.NOT_CONNECTED
        self.lock = asyncio.Lock()

    async def _send_message(self, message: str):
        async with self.lock:
            if self.streams is None:
                raise Exception("You tried to send a request before a connection to ares was made")

            try:
                reader, writer = self.streams
                writer.write(message.encode("utf-8") + b"\n")
                await asyncio.wait_for(writer.drain(), 5)

                res = await asyncio.wait_for(reader.readuntil(b"#"), 5)
                await reader.readexactly(2)

                if res == b"":
                    writer.close()
                    self.streams = None
                    self.connection_status = ConnectionStatus.NOT_CONNECTED
                    raise Exception("Connection to ares closed")

                if self.connection_status == ConnectionStatus.TENTATIVE:
                    self.connection_status = ConnectionStatus.CONNECTED

                return res.decode("utf-8")
            except asyncio.TimeoutError as exc:
                writer.close()
                self.streams = None
                self.connection_status = ConnectionStatus.NOT_CONNECTED
                raise Exception("Connection to ares timed out") from exc
            except ConnectionResetError as exc:
                writer.close()
                self.streams = None
                self.connection_status = ConnectionStatus.NOT_CONNECTED
                raise Exception("Connection to ares reset") from exc

    async def try_connect(self, port: int) -> bool:
        try:
            self.streams = await asyncio.open_connection("127.0.0.1", port)
            self.connection_status = ConnectionStatus.TENTATIVE
            return True
        except (TimeoutError, ConnectionRefusedError):
            pass

        self.streams = None
        self.connection_status = ConnectionStatus.NOT_CONNECTED
        return False


def get_ares_address(req: dict[str, Any]):
    mapping = {
        "RDRAM":      0xA000_0000,
        "ROM":        0xB000_0000,
        "System Bus": 0x0000_0000,
    }
    return req["address"] + mapping[req["domain"]]


# MAX_READ_WRITE_SIZE = {
#     range(0x0000_0000, 0xA400_0000): 4,
#     range(0xA400_0000, 0xB000_0000): 4,
#     range(0xA400_0000, 0xB000_0000): float("inf"),
# }


# def convert_read_to_messages(read: dict[str, Any]) -> str:
#     cursor = get_ares_address(read)
#     size = read["size"]
#     if cursor in RCP_RANGE
#     message = ""
#     while size > 0:
#         # ares n64 only guaranteed allows reads in groups of 1, 2, 4, or 8 bytes
#         num_bytes_to_read = 1 << (min(size, 4).bit_length() - 1)
#         message += f"+$m{hex(cursor)},{num_bytes_to_read}#00"
#         cursor += num_bytes_to_read
#         size -= num_bytes_to_read
#     return message


# def convert_write_to_messages(write: dict[str, Any]) -> str:
#     cursor = get_ares_address(write)
#     data = base64.b64decode(write["value"])
#     message = ""
#     while len(data) > 0:
#         # ares n64 only guaranteed allows writes in groups of 1, 2, or 4 bytes
#         num_bytes_to_write = 1 << (min(len(data), 4).bit_length() - 1)
#         message += f"+$m{hex(cursor)},{num_bytes_to_write}:{base64.b16encode(data[:num_bytes_to_write]).decode('ascii')}#00"
#         cursor += num_bytes_to_write
#         data = data[num_bytes_to_write:]
#     return message


# async def do_reads(ctx: AresContext, read_list: list[dict[str, Any]]) -> list[bytes]:
#     message = ""
#     if len(read_list) == 1:
#         message = convert_read_to_messages(read_list[0])
#         if read_list[0]["size"] > 4:
#             message = "+$?#00" + message + "+$c#00"
#     else:
#         message += "+$?#00"  # Pause
#         message += "".join(convert_read_to_messages(r) for r in read_list)
#         message += "+$c#00"  # Unpause

#     async with ctx.lock:
#         if ctx.streams is None:
#             raise Exception("Not connected to ares")
#         ctx.streams[1].write(message.encode("utf-8") + b"\n")
#         await asyncio.wait_for(ctx.streams[1].drain(), 5)
#         res = await asyncio.wait_for(ctx.streams[0].read(1024), 5)

#     concatenated_data = base64.b16decode("".join(s[:-3] for s in res.decode("utf-8").replace("+", "").split("$")[2:]))
#     split_data: list[bytes] = []

#     i = 0
#     cursor = 0
#     while i < len(read_list):
#         split_data.append(concatenated_data[cursor:cursor + read_list[i]["size"]])
#         cursor += read_list[i]["size"]
#         i += 1
#     return split_data


# async def do_writes(ctx: AresContext, write_list: list[dict[str, Any]]) -> bytes:
#     message = ""
#     if len(write_list) == 1:
#         value = base64.b64decode(write_list[0]["value"])
#         message = convert_write_to_messages(write_list[0])
#         if len(value) > 4:
#             message = "+$?#00" + message + "+$c#00"
#     else:
#         message += "+$?#00"  # Pause
#         message += "".join(convert_write_to_messages(w) for w in write_list)
#         message += "+$c#00"  # Unpause

#     async with ctx.lock:
#         if ctx.streams is None:
#             raise Exception("Not connected to ares")
#         ctx.streams[1].write(message.encode("utf-8") + b"\n")
#         await asyncio.wait_for(ctx.streams[1].drain(), 5)
#         res = await asyncio.wait_for(ctx.streams[0].read(1024), 5)
#         print(res)
#         raise NotImplementedError("need to validate/return")

#     # return base64.b16decode("".join(s[:-3] for s in res.decode("utf-8").replace("+", "").split("$")[2:]))


async def process_requests(requests: list[dict[str, Any]], ares_ctx: AresContext) -> list[dict[str, Any]]:
    # Pure reads
    # if all(req["type"] == "READ" for req in requests):
    #     data = await do_reads(ares_ctx, requests)
    #     return [{
    #         "type": "READ_RESPONSE",
    #         "value": base64.b64encode(d).decode("ascii"),
    #     } for d in data]

    # # Pure writes
    # if all(req["type"] == "WRITE" for req in requests):
    #     data = await do_writes(ares_ctx, requests)
    #     return [{
    #         "type": "WRITE_RESPONSE",
    #     } for _ in data]

    responses: list[dict[str, Any]] = []
    for req in requests:
        if req["type"] == "PING":
            responses.append({
                "type": "PONG",
            })
        elif req["type"] == "SYSTEM":
            responses.append({
                "type": "SYSTEM_RESPONSE",
                "value": "N64",
            })
        elif req["type"] == "PREFERRED_CORES":
            responses.append({
                "type": "PREFERRED_CORES_RESPONSE",
                "value": {},
            })
        elif req["type"] == "HASH":
            # TODO: Maybe read ROM header
            responses.append({
                "type": "HASH_RESPONSE",
                "value": "1",
            })
        elif req["type"] == "MEMORY_SIZE":
            # TODO: Implement/hardcode
            responses.append({
                "type": "MEMORY_SIZE_RESPONSE",
                "value": "1",
            })
        elif req["type"] == "GUARD":
            # TODO: Implement
            responses.append({
                "type": "GUARD_RESPONSE",
                "value": True,
                "address": req["address"],
            })
        elif req["type"] == "LOCK":
            responses.append({
                "type": "LOCKED",
            })
        elif req["type"] == "UNLOCK":
            responses.append({
                "type": "UNLOCKED",
            })
        elif req["type"] == "READ":
            message = f"+$m{hex(get_ares_address(req))[2:]},{hex(((req['size'] // 4) + 1) * 4)[2:]}#00"
            print(message)
            ares_response = await ares_ctx._send_message(message)
            print(ares_response)
            responses.append({
                "type": "READ_RESPONSE",
                # "value": base64.b64encode((await do_reads(ares_ctx, [req]))[0]).decode("ascii"),
            })
        elif req["type"] == "WRITE":
            # await do_writes(ares_ctx, [req])
            responses.append({
                "type": "WRITE_RESPONSE",
            })
        elif req["type"] == "DISPLAY_MESSAGE":
            responses.append({
                "type": "DISPLAY_MESSAGE_RESPONSE",
            })
        elif req["type"] == "SET_MESSAGE_INTERVAL":
            responses.append({
                "type": "SET_MESSAGE_INTERVAL_RESPONSE",
            })
    return responses


async def main():
    ares_ctx = AresContext()
    if not await ares_ctx.try_connect(9123):
        return
    print("Connection to ares successful")

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

                responses = await process_requests(json.loads(req_str), ares_ctx)
                writer.write(json.dumps(responses).encode("utf-8") + b"\n")
                await asyncio.wait_for(writer.drain(), 5)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(on_client_connect, "localhost", 43055)
    async with server:
        await server.serve_forever()


asyncio.run(main())
