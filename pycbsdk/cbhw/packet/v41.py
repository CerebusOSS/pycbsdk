from ctypes import *
from .common import (
    CBPacketType,
    CBManualUnitMapping,
    CBHoop,
    CBChanLowHigh,
    CBScaling,
    CBFiltDesc,
)
from .abstract import CBPacketConfigFixed
from .header import CBPacketHeader


class CBPacketSysProtocolMonitor(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        (
            "sentpkts",
            c_uint32,
        ),  # Packets sent since last cbPKT_SYSPROTOCOLMONITOR (or 0 if timestamp=0);
        # the cbPKT_SYSPROTOCOLMONITOR packets are counted as well so this must
        # be equal to at least 1
        ("counter", c_uint32),  # Counter of this type of packet
    ]

    @property
    def default_type(self):
        return CBPacketType.SYSPROTOCOLMONITOR


class CBChanMonitor(Structure):
    _fields_ = [
        ("moninst", c_uint16),  # instrument of channel to monitor
        ("monchan", c_uint16),  # channel to monitor
        ("outvalue", c_int32),  # output value
    ]


class CBChanInfoUnion(Union):
    _fields_ = [("a", CBChanMonitor), ("b", CBChanLowHigh)]


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
        ("reserved", c_uint8 * 2),
        ("triginst", c_uint8),  # instrument of the trigger channel
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
