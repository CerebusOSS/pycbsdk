import logging
import queue
import struct
import threading

from .device.base import DeviceInterface
from .packet.factory import CBPacketFactory
from .packet.common import CBSpecialChan, CBChannelType


logger = logging.getLogger(__name__)


debug_unrecognized_packets = set()
debug_packet_counter = [0]


class PacketHandlerThread(threading.Thread):
    """
    receiver_queue is filled with packets by the IO system.
    Retrieved packets are used to update device state,
    and to call the registered callback functions.
    Both state updates and callbacks must be threadsafe
    and should use atomic operations only.
    """

    def __init__(self, device: DeviceInterface, **kwargs):
        super().__init__(**kwargs)
        self._recv_q = queue.SimpleQueue()
        self._device = device
        self._continue = False
        self._packet_factory = CBPacketFactory(protocol=device._params.protocol)
        self._stop_event = threading.Event()
        self.daemon = True

    @property
    def receiver_queue(self) -> queue.SimpleQueue:
        return self._recv_q

    def run(self) -> None:
        last_group_time = -1
        last_group_data = None
        while True:
            try:
                pkt_tuple = self._recv_q.get(block=False)
            except queue.Empty:
                # Queue was empty
                if self._stop_event.wait(0.001):
                    break
                else:
                    continue
            pkt_time, chid, pkt_type, dlen, data = pkt_tuple
            self._device.pkts_received += 1

            # Update device state
            if pkt_time > self._device.last_time:
                self._device.last_time = pkt_time
                if chid == CBSpecialChan.GROUP and pkt_type == 6:
                    last_group_time = pkt_time
                    last_group_data = struct.unpack("<hh", data[:4])
            elif (
                chid == CBSpecialChan.GROUP
                and pkt_type == 6
                and pkt_time < last_group_time
            ):
                logger.warning(
                    f"Packets out of order. "
                    f"last: {last_group_time}"
                    f";\t\tlast data: {last_group_data}"
                    f";\t\tnew: {pkt_time}"
                    f";\t\tnew data: {struct.unpack('<hh', data[:4])}"
                    f";\t\tdelta t: {(pkt_time - last_group_time) / 1e9}"
                    f";\t\tpkt type: {pkt_type}"
                    f";\t\tpkts seen: {self._device.pkts_received}"
                )

            # Get the channel type for this channel. Note that we will only have meaningful chantype values for channels
            #  that returned a chaninfo (see _handle_chaninfo). For all other chids (i.e., `0` and `0x8000`) we will get
            #  the default value: ANY; this packet does not belong to a single channel.
            chantype = self._device.config["channel_types"][chid]

            b_debug_unknown = True  # If there are no callbacks and it's not a group or event packet, then debug.

            # See if we have any callbacks registered for this type of packet.
            b_grp = False
            if chid & CBSpecialChan.CONFIGURATION:
                callbacks = self._device.config_callbacks[pkt_type]
            elif chid == CBSpecialChan.GROUP:
                # This is a sample group packet. The pkt_type is actually the sample group id (1-6)
                if pkt_type in self._device.group_callbacks:
                    b_grp = True
                    callbacks = self._device.group_callbacks[pkt_type]
                else:
                    # Known bug https://blackrockengineering.atlassian.net/browse/CSCI-95
                    callbacks = None
                b_debug_unknown = False
            else:
                callbacks = self._device.event_callbacks[chantype]
                if chantype != CBChannelType.Any:
                    callbacks += self._device.event_callbacks[CBChannelType.Any]
                b_debug_unknown = False

            # Only bother to construct the packet if we have a callback registered.
            # Note: the NSPDevice registers some of its own callbacks to handle config packets it is monitoring.
            #  See _register_basic_callbacks.
            #  Otherwise, a callback will only be registered if client code called register_XXX_callback
            if callbacks:
                pkt = self._packet_factory.make_packet(
                    data, chid=chid, pkt_type=pkt_type, chantype=chantype
                )
                if b_grp:
                    # Note: pkt.data length is always a multiple of 4 bytes = 32 bits = 2 channels * 16 bits.
                    n_chans = self._device.config["group_nchans"][pkt_type]
                    if n_chans % 2 != 0:
                        #  Odd number of channels enabled then we have an extra 16 bits of data.
                        pkt.data = pkt.data[:n_chans]
                # Between the time the callbacks are grabbed above and the time we actually call them,
                #  it's possible for the client to unregister the callback.
                # Thus it's very important that a callback is unregistered and some time is allowed to pass
                #  before the objects supporting the callback are destroyed.
                for cb in callbacks:
                    # self._main_loop.call_soon_threadsafe(cb, pkt)
                    cb(pkt)
            elif b_debug_unknown:
                # We can use this to debug receiving packet types we are unfamiliar with.
                pkt = self._packet_factory.make_packet(
                    data, chid=chid, pkt_type=pkt_type, chantype=chantype
                )
                self.warn_unhandled(pkt)

        del self._recv_q
        self._recv_q = None

    def stop(self):
        self._stop_event.set()

    @staticmethod
    def warn_unhandled(pkt):
        debug_packet_counter[0] = debug_packet_counter[0] + 1
        if (debug_packet_counter[0] % 100) == 0:
            logger.warning(f"Received {debug_packet_counter[0]}'th unhandled packet.")

        _old = len(debug_unrecognized_packets)
        debug_unrecognized_packets.add(pkt.header.type)
        if len(debug_unrecognized_packets) > _old:
            logger.warning(
                f"Received unhandled packet with type {hex(pkt.header.type)}"
            )
