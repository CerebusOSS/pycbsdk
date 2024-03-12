from ctypes import *
from typing import Type
from .. import config
from .common import CBPacketType, CBChannelType, CBSpecialChan

# Note, we cannot import anything in the top-level ..packet module
# until after config.protocol is set during CBPacketFactory init.
# Submodules are OK.


class CBPacketFactory:
    def __init__(self, protocol="4.1"):
        config.protocol = protocol
        self._pktcls_by_type = {}
        self._pktcls_by_chantype = {}
        self._fallback_class = None

        from ..packet.packets import register_pktcls_with_factory, CBPacketHeader

        self.header_cls = CBPacketHeader
        self.header_size = sizeof(self.header_cls)
        register_pktcls_with_factory(self)

    def register_pktcls_by_header_types(
        self, pkt_types: list[CBPacketType], pkt_class: Type[Structure]
    ):
        """
        Associate one-or-more config packet header.types with a Packet Class.
        :param pkt_types: The packet header's type.
        :param pkt_class: The packet class.
        """
        if not isinstance(pkt_types, list):
            pkt_types = [pkt_types]
        for pkt_type in pkt_types:
            self._pktcls_by_type[pkt_type] = pkt_class

    def register_pktcls_by_channel_type(
        self, chan_type: CBChannelType, pkt_class: Type[Structure]
    ):
        """
        Associate a channel type with a packet class.
        :param chan_type:
        :param pkt_class:
        :return:
        """
        self._pktcls_by_chantype[chan_type] = pkt_class

    def register_fallback_packet_class(self, pkt_class: Type[Structure]):
        self._fallback_class = pkt_class

    def make_packet(
        self,
        data: bytes,
        chid: int = None,
        pkt_type: int = None,
        chantype: CBChannelType = None,
    ) -> Type[Structure]:
        # chid is 0x8000 for config packets, or another non-zero value for event (spike, comment, etc) packets.
        # It is 0 for sample group packets.
        if not chid:
            header = self.header_cls.from_buffer_copy(data[: self.header_size])
            chid = header.chid
            pkt_type = header.type
        """
        The logic to figure out the packet type is a bit complicated.
        This first link provides a good example of how to determine which kind of config packet.
        https://github.com/CerebusOSS/CereLink/blob/d44059636a94e7752a242a9840451ec54a091f01/cbhwlib/InstNetwork.cpp#L140-L380
        This second link has other packet types too, but uses comparisons that are different to the official comparisons
        The Blackrock source should be consulted instead. 
        https://github.com/CerebusOSS/CereLink/blob/d44059636a94e7752a242a9840451ec54a091f01/cbmex/cbsdk.cpp#L4114-L4170
        """
        pkt_cls = None
        if chid & CBSpecialChan.CONFIGURATION:
            # Configuration packets. We can usually figure out what kind of config packet by its type.
            if pkt_type in self._pktcls_by_type:
                pkt_cls = self._pktcls_by_type[pkt_type]
            elif (pkt_type & 0xF0) in self._pktcls_by_type:
                # Some packet types serve multiple header pkt_type, but they share the same first byte.
                pkt_cls = self._pktcls_by_type[pkt_type & 0xF0]
            elif self._fallback_class is not None:
                # Unknown configuration packet. This should probably be a generic packet.
                pkt_cls = self._fallback_class
        elif chantype and chantype in self._pktcls_by_chantype:
            # The caller provided us with a channel type to use, from the device's map of channels to types.
            #  This line is only hit when manually constructing packets for sending.
            pkt_cls = self._pktcls_by_chantype[chantype]
        elif pkt_type > 0:
            # Sample group. pkt_type is the sampling group.
            pkt_cls = self._pktcls_by_chantype[CBChannelType.Group]
        elif self._fallback_class is not None:
            pkt_cls = self._fallback_class
        if pkt_cls is None:
            raise ValueError(
                "No factory function for packet type %s (%s) and channel %d",
                CBPacketType(pkt_type),
                hex(pkt_type),
                chid,
            )
        try:
            pkt = pkt_cls(data)
            if data is None:
                pkt.header.chid = chid
                pkt.header.type = pkt_type
        except ValueError:
            n_missing = sizeof(pkt_cls) - len(data)
            if n_missing:
                # The firmware truncates struct sizes to the previous multiple of 4 bytes before sending them over
                #  the wire. If our packet struct definition is not a multiple of 4 then we will get a truncated
                #  packet and we need to pad to get it to the right size. Currently only the cbPKT_CHANINFO
                #  is affected by this.
                pkt = pkt_cls.from_buffer_copy(data + b"\x00" * n_missing)
            elif True:
                # Some helpful debug code.
                cumu_bytes = 0
                for f, t in pkt_cls._fields_:
                    a = getattr(pkt_cls, f)
                    print(f, a, cumu_bytes)
                    try:
                        obj = t.from_buffer_copy(data, cumu_bytes)
                        print(obj)
                    except ValueError:
                        n_missing = sizeof(t) - (len(data) - cumu_bytes)
                        print(f"Missing {n_missing} bytes in data.")
                        obj = t.from_buffer_copy(data + b"\x00", cumu_bytes)
                        for _h in obj:
                            for __h in _h:
                                print(__h.time, __h.min, __h.max)
                    cumu_bytes += a.size
                    if "label" in f:
                        print(obj.value)
                    elif "unitmapping" in f:
                        print([_.nOverride for _ in obj])
                pkt = None
            else:
                raise
        return pkt
