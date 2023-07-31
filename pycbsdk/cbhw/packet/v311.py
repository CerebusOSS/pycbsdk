from ctypes import *
import struct
from .common import (
    CBPacketType,
    CBSpecialChan,
    CBChanInfoUnion,
    CBManualUnitMapping,
    CBHoop,
    CBScaling,
    CBFiltDesc,
)
from .abstract import CBPacketVarDataNDArray, CBPacketVarLen, CBPacketConfigFixed
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
    ]

    @property
    def default_type(self):
        return CBPacketType.SYSSET


class CBPacketSysProtocolMonitor(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        (
            "sentpkts",
            c_uint32,
        )  # Packets sent since last cbPKT_SYSPROTOCOLMONITOR (or 0 if timestamp=0);
        # the cbPKT_SYSPROTOCOLMONITOR packets are counted as well so this must
        # be equal to at least 1
    ]

    @property
    def default_type(self):
        return CBPacketType.SYSPROTOCOLMONITOR


class CBPacketChanInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("chan", c_uint32),  # actual channel id of the channel being configured
        ("proc", c_uint32),  # the address of the processor on which the channel resides
        ("bank", c_uint32),  # the address of the bank on which the channel resides
        ("term", c_uint32),  # the terminal number of the channel within it's bank
        ("chancaps", c_uint32),  # general channel capablities (given by cbCHAN_* flags)
        (
            "doutcaps",
            c_uint32,
        ),  # digital output capablities (composed of cbDOUT_* flags)
        (
            "dinpcaps",
            c_uint32,
        ),  # digital input capablities (composed of cbDINP_* flags)
        (
            "aoutcaps",
            c_uint32,
        ),  # analog output capablities (composed of cbAOUT_* flags)
        ("ainpcaps", c_uint32),  # analog input capablities (composed of cbAINP_* flags)
        ("spkcaps", c_uint32),  # spike processing capabilities
        ("physcalin", CBScaling),  # physical channel scaling information
        ("phyfiltin", CBFiltDesc),  # physical channel filter definition
        ("physcalout", CBScaling),  # physical channel scaling information
        ("phyfiltout", CBFiltDesc),  # physical channel filter definition
        (
            "label",
            c_char * 16,
        ),  # Label of the channel (null terminated if <16 characters)
        ("userflags", c_uint32),  # User flags for the channel state
        ("position", c_int32 * 4),  # reserved for future position information
        ("scalin", CBScaling),  # user-defined scaling information for AINP
        ("scalout", CBScaling),  # user-defined scaling information for AOUT
        ("doutopts", c_uint32),  # digital output options (composed of cbDOUT_* flags)
        ("dinpopts", c_uint32),  # digital input options (composed of cbDINP_* flags)
        ("aoutopts", c_uint32),  # analog output options
        ("eopchar", c_uint32),  # digital input capablities (given by cbDINP_* flags)
        ("union", CBChanInfoUnion),
        ("trigtype", c_uint8),  # trigger type (see cbDOUT_TRIGGER_*)
        ("trigchan", c_uint16),  # trigger channel
        ("trigval", c_uint16),  # trigger value
        ("ainpopts", c_uint32),  # analog input options (composed of cbAINP* flags)
        ("lncrate", c_uint32),  # line noise cancellation filter adaptation rate
        ("smpfilter", c_uint32),  # continuous-time pathway filter id
        ("smpgroup", c_uint32),  # continuous-time pathway sample group
        ("smpdispmin", c_int32),  # continuous-time pathway display factor
        ("smpdispmax", c_int32),  # continuous-time pathway display factor
        ("spkfilter", c_uint32),  # spike pathway filter id
        ("spkdispmax", c_int32),  # spike pathway display factor
        ("lncdispmax", c_int32),  # Line Noise pathway display factor
        ("spkopts", c_uint32),  # spike processing options
        ("spkthrlevel", c_int32),  # spike threshold level
        ("spkthrlimit", c_int32),
        (
            "spkgroup",
            c_uint32,
        ),  # NTrodeGroup this electrode belongs to - 0 is single unit, non-0 indicates a multi-trode grouping
        ("amplrejpos", c_int16),  # Amplitude rejection positive value
        ("amplrejneg", c_int16),  # Amplitude rejection negative value
        ("refelecchan", c_uint32),  # Software reference electrode channel
        ("unitmapping", CBManualUnitMapping * 5),  # manual unit mapping
        ("spkhoops", CBHoop * 5 * 4),  # spike hoop sorting set
    ]

    @property
    def default_type(self):
        return CBPacketType.CHANSET


class CBPacketDIn(CBPacketVarDataNDArray):
    _fields_ = [("header", CBPacketHeader)]
    _array = (c_uint32 * 0)()

    @property
    def default_type(self):
        return 0x00

    @property
    def default_chid(self) -> int:
        return 279  # Best to figure this out in the calling function using chancaps.

    @property
    def data(self):
        return self._array[: self.header.dlen]

    @data.setter
    def data(self, value: list[int]):
        # It would be nice to use the array memory directly, but it's not a c_uint32 array,
        #   so we have to copy its elements (*value).
        assert len(value) <= self.max_elements
        self._array = (self._array._type_ * len(value))(*value)
        self._update_dlen()


class CBPacketNPlay(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("ftime", c_uint32),
        ("stime", c_uint32),
        ("etime", c_uint32),
        ("val", c_uint32),
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
        ("flags", c_uint8),  # Can be any of cbCOMMENT_FLAG_*
        ("reserved", c_uint8 * 2),  # Reserved (must be 0)
    ]


class CBPacketComment(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("info", CBCommentInfo),
        ("data", c_uint32),  # depends on flags (see flags above)
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

    @property
    def rgba(self):
        return (
            (0, 0, 0, 1)
            if self.flags
            else struct.unpack("4B", struct.pack("I", self.data))
        )

    @rgba.setter
    def rgba(self, value: tuple):
        self.data = struct.unpack("I", struct.pack("4B", *value))
        self.flags = 0x00

    @property
    def timeStarted(self):
        return self.data if self.flags else -1

    @timeStarted.setter
    def timeStarted(self, value: int):
        self.data = value
        self.flags = 0x01
