import asyncio
import logging
import queue
import socket
import struct
import threading
from typing import Optional, Tuple

from pycbsdk.cbhw.packet.factory import CBPacketFactory
from .base import CerebusCommInterface


logger = logging.getLogger(__name__)


class FlexiQueue:
    """
    https://stackoverflow.com/a/59650685
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        self._loop = loop if loop is not None else asyncio.get_running_loop()
        self._queue = asyncio.Queue()

    def sync_put_nowait(self, item):
        self._loop.call_soon(self._queue.put_nowait, item)

    def sync_put(self, item):
        asyncio.run_coroutine_threadsafe(self._queue.put(item), self._loop).result()

    def sync_get(self):
        return asyncio.run_coroutine_threadsafe(self._queue.get(), self._loop).result()

    def async_put_nowait(self, item):
        self._queue.put_nowait(item)

    async def async_put(self, item):
        await self._queue.put(item)

    async def async_get(self):
        return await self._queue.get()


class CerebusDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        on_con_lost: asyncio.Future,
        protocol: str,
        receiver_queue: queue.SimpleQueue,
    ):
        self._on_con_lost = on_con_lost
        self._packet_factory = CBPacketFactory(protocol=protocol)  # Just for the header
        self._recv_queue = receiver_queue

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        hdr_tuples_data = self._process_datagram(data)
        for hdr_tuple in hdr_tuples_data:
            pkt_time, chid, pkt_type, dlen = hdr_tuple[:4]
            # v4 has instrument and reserved in hdr_tuple[4:6]
            data = hdr_tuple[-1]
            self._recv_queue.put((pkt_time, chid, pkt_type, dlen, data))

    def error_received(self, exc: Exception) -> None:
        logger.error("Error received: ", exc)

    def connection_lost(self, exc: Exception) -> None:
        logger.debug("Data receiver connection closed.")
        try:
            if not self._on_con_lost.done():
                self._on_con_lost.set_result(True)
        except asyncio.InvalidStateError:
            logger.warning("Connection future already set.")

    def _process_datagram(self, data: bytes) -> list[int, int, int, bytes]:
        """
        :param data:
        :return: a list of (chid, pkt_type, pkt_data) tuples
        """
        #
        known_tuples = []
        header_size = self._packet_factory.header_size
        header_format = self._packet_factory.header_cls.HEADER_FORMAT
        while len(data) >= header_size:
            header_tuple = struct.unpack(header_format, data[:header_size])
            dlen = header_tuple[3]
            known_tuples.append(header_tuple + (data[: header_size + dlen * 4],))
            data = data[header_size + dlen * 4 :]
        return known_tuples


class CerebusDatagramThread(threading.Thread, CerebusCommInterface):
    """
    Runs the receiver and sender async chains.
    """

    def __init__(
        self,
        receiver_queue: queue.SimpleQueue,
        receiver_interface_addr: Tuple[str, int],
        device_interface_addr: Tuple[str, int],
        protocol_version: str,
        buff_size: int,
    ):
        super().__init__()
        self._recv_q = receiver_queue
        self._recv_addr = receiver_interface_addr
        self._dev_addr = device_interface_addr
        self._proto_ver = protocol_version
        self._buff_size = buff_size
        self._send_q: Optional[FlexiQueue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._transport: Optional[asyncio.transports.BaseTransport] = None

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._send_q = FlexiQueue(self._loop)
        self._loop.run_until_complete(
            asyncio.gather(self._receiver_coro(), self._sender_coro())
        )
        self._send_q = None

    def stop(self) -> None:
        self._transport.close()
        self.send("quit")

    def send(self, send_bytes):
        """
        Called by main thread.
        """
        if self._send_q is None:
            logger.error(
                "Cannot send bytes to devices because the io thread is not running"
            )
            return
        self._send_q.sync_put(send_bytes)

    async def _receiver_coro(self):
        # Create socket
        sock = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
        )
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_DONTROUTE, True)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._buff_size)
        # sock.settimeout(10)
        # sock.setblocking(False)
        sock.bind(self._recv_addr)

        loop = asyncio.get_event_loop()
        # Create a future that should only return when the UDP connection is lost
        conn_lost_future = loop.create_future()
        # Create the UDP connection. Upon connection, it will invoke the NSPProtocol.
        self._transport, protocol = await loop.create_datagram_endpoint(
            lambda: CerebusDatagramProtocol(
                conn_lost_future, self._proto_ver, self._recv_q
            ),
            # local_addr=self._local_addr,
            # remote_addr=self._dev_addr,
            sock=sock,
        )
        await conn_lost_future
        # We might reach here when the remote disconnects (i.e., not when the client quits).
        # In such cases, we must also kill sender_coro.
        await self._send_q.async_put("quit")

    async def _sender_coro(self):
        while self._transport is None:
            await asyncio.sleep(0.1)

        running = True
        while running:
            message = await self._send_q.async_get()
            if message == "quit":
                running = False
            elif message:
                self._transport.sendto(message, addr=self._dev_addr)
