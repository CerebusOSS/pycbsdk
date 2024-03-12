from ctypes import *
from .common import CBPacketType, CBSpecialChan
from .abstract import CBPacketVarLen, CBPacketConfigFixed
from .header import CBPacketHeader


# -- Packets that have changed in this version --


class CBPacketDIn(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("valueRead", c_uint32),  # data read from the digital input port
        ("bitsChanged", c_uint32),  # bits that have changed from the last packet sent
        (
            "eventType",
            c_uint32,
        ),  # type of event, eg DINP_EVENT_ANYBIT, DINP_EVENT_STROBE
    ]

    @property
    def default_type(self):
        return 0x00

    @property
    def default_chid(self) -> int:
        return 279  # Just a guess. Best to figure this out in the calling function using chancaps


class CBPacketNPlay(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("ftime", c_uint64),
        ("stime", c_uint64),
        ("etime", c_uint64),
        ("val", c_uint64),
        ("mode", c_uint16),
        ("flags", c_uint16),
        ("speed", c_float),
    ]
    _array = (c_char * 0)()

    @property
    def default_type(self):
        return CBPacketType.NPLAYSET

    @property
    def default_chid(self) -> int:
        return CBSpecialChan.CONFIGURATION

    @property
    def max_elements(self):
        return 992

    @property
    def opt(self) -> int:
        return self.ftime

    @opt.setter
    def opt(self, inopt: int):
        self.ftime = inopt

    @property
    def fname(self) -> str:
        return self._array[: self.max_elements].decode("utf-8")

    @fname.setter
    def fname(self, infname: str):
        assert len(infname) <= self.max_elements
        self._array = (self._array._type_ * len(infname))()
        self._array[: len(infname)] = infname.encode("utf-8")


class CBCommentInfo(Structure):
    _pack_ = 1
    _fields_ = [
        (
            "charset",
            c_uint8,
        ),  # Character set (0 - ANSI, 1 - UTF16, 255 - NeuroMotive ANSI)
        ("reserved", c_uint8 * 3),  # Reserved (must be 0)
    ]


class CBPacketComment(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("info", CBCommentInfo),
        ("timeStarted", c_uint64),
        ("rgba", c_uint32),  # depends on flags (see flags above)
    ]
    _array = (
        c_char * 0
    )()  # Supposed to be variable length, but seems like it is always padded out to 128.

    @property
    def default_type(self):
        return CBPacketType.COMMENTSET

    @property
    def default_chid(self):
        return CBSpecialChan.CONFIGURATION

    @property
    def max_elements(self) -> int:
        return 128

    @property
    def comment(self) -> str:
        # codec = {0: 'ANSI', 1: 'UTF16', 255: 'ANSI'}[self.charset]
        # ''.join([_.decode(codec) for _ in res[4:]]).rstrip('\x00')
        return self._array.rstrip("\x00")  # TODO: Decode?

    @comment.setter
    def comment(self, incomment: str):
        ll = len(incomment)
        assert ll <= self.max_elements
        if False:
            # If it's really constant length 128
            assert ll <= len(self._array)
            self._array = list(incomment) + [b"\x00"] * (
                len(self._array) - ll
            )  # TODO: encode?
        else:
            self._array = (self._array._type_ * len(incomment))()
            memmove(self._array, incomment, len(incomment))
        self._update_dlen()
