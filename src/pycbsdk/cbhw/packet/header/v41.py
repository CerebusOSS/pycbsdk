from ctypes import *
from ..common import print_pretty


@print_pretty
class CBPacketHeader(Structure):
    _pack_ = 1
    _fields_ = [
        ("time", c_uint64),
        ("chid", c_uint16),  # Channel ID. 1-based. See CBSpecialChan for special chids.
        ("type", c_uint16),  # Packet type. Changed in this version from c_uint8
        (
            "dlen",
            c_uint16,
        ),  # Number of 32-bit elements in packet body. * 4 to get number of bytes.
        ("instrument", c_uint8),
        ("reserved", c_uint8),  # Changed in this version; used to be 2 * c_uint8
    ]

    @classmethod
    @property
    def HEADER_FORMAT(cls):
        return "<QHHHBB"
