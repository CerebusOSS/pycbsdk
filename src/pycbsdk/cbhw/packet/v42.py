from ctypes import *
from .common import (
    CBPacketType,
)
from .abstract import CBPacketConfigFixed
from .header import CBPacketHeader


class CBPacketSysInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("sysfreq", c_uint32),  # System clock frequency in Hz
        ("spikelen", c_uint32),  # The length of the spike events
        ("spikepre", c_uint32),  # Spike pre-trigger samples
        ("resetque", c_uint32),  # The channel for the reset to que on
        ("runlevel", c_uint32),  # System runlevel
        ("runflags", c_uint32),
        ("transport", c_uint16),
        ("reserved", c_uint8 * 2),
    ]

    @property
    def default_type(self):
        return CBPacketType.SYSSET
