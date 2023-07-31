from ctypes import *


class CBPacketHeader(Structure):
    _pack_ = 1
    _fields_ = [
        ("time", c_uint32),
        ("chid", c_uint16),  # Channel ID. 1-based. See CBSpecialChan for special chids.
        ("type", c_uint8),
        (
            "dlen",
            c_uint8,
        ),  # Number of 32-bit elements in packet body. * 4 to get number of bytes.
    ]

    @classmethod
    @property
    def HEADER_FORMAT(cls):
        return "<LHBB"
