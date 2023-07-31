import typing
from ctypes import *
import struct
import numpy as np
import numpy.typing
from .. import config
from .common import CBChannelType, CBPacketType, CBSpecialChan, CBManualUnitMapping
from .abstract import CBPacketVarDataNDArray, CBPacketVarLen, CBPacketConfigFixed

if config.protocol is None:
    raise ValueError(
        "config.protocol must be set before importing from pycbsdk.cbhw.packet top-level module."
    )

# Import structures that have changed over protocol versions using the most recent for this config.protocol
from .header import CBPacketHeader  # header/__init__ handles the version check

# CBPacketDIn, CBPacketNPlay, CBPacketComment changed in 4.0
if int(config.protocol[0]) < 4:
    from .v311 import CBPacketDIn, CBPacketNPlay, CBPacketComment
else:
    from .v40 import CBPacketDIn, CBPacketNPlay, CBPacketComment

# CBPacketSysProtocolMonitor, CBPacketChanInfo changed in 4.1
if int(config.protocol[0]) < 4 or int(config.protocol.split(".")[1]) < 1:
    from .v311 import CBPacketSysProtocolMonitor, CBPacketChanInfo
else:
    from .v41 import CBPacketSysProtocolMonitor, CBPacketChanInfo

# CBPacketSysInfo changed in 4.2
if int(config.protocol[0]) < 4 or int(config.protocol.split(".")[1]) < 2:
    from .v311 import CBPacketSysInfo
else:
    from .v42 import CBPacketSysInfo


# Only export a selection of symbols. i.e. the header and the concrete packet types
__all__ = [
    "CBPacketHeader",
    "CBPacketHeartBeat",
    "CBPacketSysInfo",
    "CBPacketSysProtocolMonitor",
    "CBPacketProcInfo",
    "CBPacketGroup",
    "CBPacketSpike",
    "CBPacketChanInfo",
    "CBPacketComment",
    "CBPacketSysProtocolMonitor",
    "CBPacketRefElecFiltInfo",
    "CBPacketLNC",
    "CBPacketFileCFG",
    "CBPacketVideoTrack",
    "CBPacketVideoSynch",
    "CBPacketNPlay",
    "CBPacketSSModelAll",
    "register_pktcls_with_factory",
]


# -- Concrete Packet Types -- #
# Note: All concrete packet types start with `_fields_`
class CBPacketSpike(CBPacketVarDataNDArray):
    _fields_ = [
        ("header", CBPacketHeader),
        ("_fPattern", c_float * 3),
        ("nPeak", c_int16),
        ("nValley", c_int16),
    ]
    _array = (c_int16 * 0)()  # *0 allows this to be variable.

    # TODO: Static method to update static spklen for decode/encode. Only need to be set when device spklen changes.

    @property
    def default_type(self):
        return 0x00

    @property
    def default_chid(self):
        return 1

    @property
    def max_elements(self):
        return 128

    @property
    def fPattern(self) -> list[int]:
        return list(self._fPattern)

    @fPattern.setter
    def fPattern(self, value: list[int]):
        self._fPattern = (self._fPattern._type_ * 3)(*value)

    # header type is reused as sorted-unit identifier.
    @property
    def unit(self) -> int:
        # TODO: Enum of possible unit ids: 0, 1, 2, 3, 4, 5, 255
        return self.header.type

    @unit.setter
    def unit(self, value: int):
        self.header.type = value

    @property
    def wave(self) -> np.ndarray[typing.Any, np.dtype[np.int16]]:
        return self.data

    @wave.setter
    def wave(self, indata: numpy.typing.ArrayLike):
        self.data = indata


class CBPacketGroup(CBPacketVarDataNDArray):
    _fields_ = [("header", CBPacketHeader)]
    _array = (c_int16 * 0)()  # dtype is v3.x: int16; v4.x: A2_DATA.

    @property
    def default_type(self):
        return 0x00

    @property
    def default_chid(self):
        return 0x0000

    @property
    def max_elements(self):
        return 272  # TODO: Read from static that is set by device.

    @property
    def group_id(self) -> int:
        return self.header.type

    @group_id.setter
    def group_id(self, value: int):
        self.header.type = value


class CBPacketGeneric(CBPacketVarLen):
    _fields_ = [("header", CBPacketHeader)]
    _array = (c_uint32 * 0)()

    @property
    def max_elements(self) -> int:
        return (1024 - sizeof(CBPacketHeader)) // 4

    @property
    def default_chid(self) -> int:
        return 0

    @property
    def default_type(self):
        return CBPacketType.SYSHEARTBEAT  # 0x00

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


class CBPacketHeartBeat(CBPacketGeneric):
    @property
    def max_elements(self) -> int:
        return 0


# ---
# Config Packets -- Fixed Size
# ---
class CBPacketSetDOut(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        (
            "chan",
            c_uint16,
        ),  # Which digital output channel (1 based, will equal chan from GetDoutCaps)
        (
            "value",
            c_uint16,
        ),  # Which value to set? zero = 0; non-zero = 1 (output is 1 bit)
    ]

    @property
    def default_type(self):
        return CBPacketType.SET_DOUTSET


class CBPacketGroupInfo(CBPacketVarDataNDArray):
    _fields_ = [
        ("header", CBPacketHeader),
        ("proc", c_uint32),
        ("group", c_uint32),
        ("label", c_char * 16),  # Sampling group label
        ("period", c_uint32),  # Sampling period for the group
        ("length", c_uint32),  # Number of channels in group
    ]
    _array = (c_uint16 * 0)()  # Channel membership in group

    @property
    def default_chid(self) -> int:
        return CBSpecialChan.CONFIGURATION

    @property
    def default_type(self):
        return CBPacketType.GROUPSET

    @property
    def max_elements(self) -> int:
        return 272

    @property
    def chan_list(self) -> np.ndarray[typing.Any, np.dtype[np.uint16]]:
        return self.data[: self.length]

    @chan_list.setter
    def chan_list(self, indata: numpy.typing.ArrayLike):
        self.data = indata


class CBPacketFiltInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("proc", c_uint32),
        ("filt", c_uint32),
        ("_label", c_char * 16),
        ("hpfreq", c_uint32),  # high-pass corner frequency in milliHertz
        ("hporder", c_uint32),  # high-pass filter order
        ("hptype", c_uint32),  # high-pass filter type
        ("lpfreq", c_uint32),  # low-pass frequency in milliHertz
        ("lporder", c_uint32),  # low-pass filter order
        ("lptype", c_uint32),  # low-pass filter type
        ("gain", c_double),  # filter gain
        ("sos1a1", c_double),  # filter coefficients for second-order-section
        ("sos1a2", c_double),
        ("sos1b1", c_double),
        ("sos1b2", c_double),
        ("sos2a1", c_double),
        ("sos2a2", c_double),
        ("sos2b1", c_double),
        ("sos2b2", c_double),
    ]

    @property
    def default_type(self):
        return CBPacketType.FILTSET

    @property
    def label(self) -> str:
        return self._label.rstrip("\x00")  # TODO: Decode?

    @label.setter
    def label(self, inlabel: str):
        ll = len(inlabel)
        assert ll <= 16
        self._label = list(inlabel) + [b"\x00"] * (16 - ll)  # TODO: encode inlabel


class CBPacketProcInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("proc", c_uint32),  # index of the bank.
        (
            "idcode",
            c_uint32,
        ),  # manufacturer part and rom ID code of the Signal Processor
        (
            "_ident",
            c_char * 64,
        ),  # ID string with the equipment name of the Signal Processor
        (
            "chanbase",
            c_uint32,
        ),  # lowest channel number of channel id range claimed by this processor
        (
            "chancount",
            c_uint32,
        ),  # number of channel identifiers claimed by this processor
        ("bankcount", c_uint32),  # number of signal banks supported by the processor
        ("groupcount", c_uint32),  # number of sample groups supported by the processor
        ("filtcount", c_uint32),  # number of digital filters supported by the processor
        (
            "sortcount",
            c_uint32,
        ),  # number of channels supported for spike sorting (reserved for future)
        (
            "unitcount",
            c_uint32,
        ),  # number of supported units for spike sorting    (reserved for future)
        (
            "hoopcount",
            c_uint32,
        ),  # number of supported hoops for spike sorting    (reserved for future)
        ("sortmethod", c_uint32),  # sort method  (0=manual, 1=automatic spike sorting)
        ("version", c_uint32),  # current version of libraries
    ]

    @property
    def default_type(self):
        return CBPacketType.PROCREP

    @property
    def ident(self) -> str:
        return self._ident.decode("utf-8")

    @ident.setter
    def ident(self, inident: str):
        ll = len(inident)
        assert ll <= len(self._ident)
        self._ident = list(inident) + [b"\x00"] * (
            len(self._ident) - ll
        )  # TODO: encode?


class CBPacketBankInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("proc", c_uint32),  # the address of the processor on which the bank resides
        ("bank", c_uint32),  # the address of the bank reported by the packet
        (
            "idcode",
            c_uint32,
        ),  # manufacturer part and rom ID code of the module addressed to this bank
        (
            "_ident",
            c_char * 64,
        ),  # ID string with the equipment name of the Signal Bank hardware module
        (
            "_label",
            c_char * 16,
        ),  # Label on the instrument for the signal bank, eg "Analog In"
        (
            "chanbase",
            c_uint32,
        ),  # lowest channel number of channel id range claimed by this bank
        ("chancount", c_uint32),  # number of channel identifiers claimed by this bank
    ]

    @property
    def default_type(self):
        return CBPacketType.BANKREP

    @property
    def ident(self) -> str:
        return self._ident.rstrip("\x00")  # TODO: Decode?

    @ident.setter
    def ident(self, inident: str):
        ll = len(inident)
        assert ll <= len(self._ident)
        self._ident = list(inident) + [b"\x00"] * (
            len(self._ident) - ll
        )  # TODO: encode?

    @property
    def label(self) -> str:
        return self._label.rstrip("\x00")  # TODO: Decode?

    @label.setter
    def label(self, inlabel: str):
        ll = len(inlabel)
        assert ll <= len(self._label)
        self._label = list(inlabel) + [b"\x00"] * (
            len(self._label) - ll
        )  # TODO: encode?


class CBPacketNTrodeInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("ntrode", c_uint32),  # ntrode with which we are working (1-based)
        (
            "_label",
            c_char * 16,
        ),  # Label of the Ntrode (null terminated if < 16 characters)
        ("ellipses", CBManualUnitMapping * 6 * 5),
        (
            "nSite",
            c_uint16,
        ),  # number channels in this NTrode ( 0 <= nSite <= cbMAXSITES)
        ("fs", c_uint16),  # NTrode feature space cbNTRODEINFO_FS_*
        ("nchan", c_uint16 * 4),  # group of channels in this NTrode
    ]

    @property
    def default_type(self):
        return CBPacketType.SETNTRODEINFO


class CBPacketAdaptFiltInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("chan", c_uint32),  # ignored
        (
            "nMode",
            c_uint32,
        ),  # 0=disabled, 1=filter continuous & spikes, 2=filter spikes
        (
            "dLearningRate",
            c_float,
        ),  # speed at which adaptation happens. Very small. e.g. 5e-12
        ("nRefChan1", c_uint32),  # The first reference channel (1 based).
        ("nRefChan2", c_uint32),  # The second reference channel (1 based).
    ]

    @property
    def default_type(self):
        return CBPacketType.ADAPTFILTSET


class CBPacketRefElecFiltInfo(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("chan", c_uint32),  # Ignored
        (
            "nMode",
            c_uint32,
        ),  # 0=disabled, 1=filter continuous & spikes, 2=filter spikes
        ("nRefChan", c_uint32),  # The reference channel (1 based).
    ]

    @property
    def default_type(self):
        return CBPacketType.REFELECFILTSET


class CBPacketLNC(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("lncFreq", c_uint32),  # Nominal line noise frequency to be canceled  (in Hz)
        ("lncRefChan", c_uint32),  # Reference channel for lnc synch (1-based)
        ("lncGlobalMode", c_uint32),  # reserved
    ]

    @property
    def default_type(self):
        return CBPacketType.LNCSET


class CBPacketFileCFG(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("options", c_uint32),  # cbFILECFG_OPT_*
        ("duration", c_uint32),
        (
            "recording",
            c_uint32,
        ),  # If cbFILECFG_OPT_NONE this option starts/stops recording remotely
        (
            "extctrl",
            c_uint32,
        ),  # If cbFILECFG_OPT_REC this is split number (0 for non-TOC)
        # If cbFILECFG_OPT_STOP this is error code (0 means no error)
    ]
    _array = (c_char * 0)()

    @property
    def max_elements(self) -> int:
        return 256 + 256 + 256

    @property
    def default_chid(self) -> int:
        return CBSpecialChan.CONFIGURATION

    @property
    def default_type(self):
        return CBPacketType.SETFILECFG

    @property
    def username(self) -> str:
        # Check dlen or check sizeof self._array ?
        if self._array_nbytes > 0:
            return self._array[:256].decode("utf-8")
        else:
            return ""

    @property
    def filename(self) -> str:
        if self._array_nbytes > 256:
            return self._array[256:512].decode("utf-8")
        else:
            return ""

    @property
    def comment(self) -> str:
        if self._array_nbytes > 512:
            return self._array[512:768].decode("utf-8")
        else:
            return ""


class CBPacketVideoTrack(CBPacketVarDataNDArray):
    _fields_ = [
        ("header", CBPacketHeader),
        ("parentID", c_uint16),
        ("nodeID", c_uint16),  # (cross-referenced in the TrackObj header)
        ("nodeCount", c_uint16),  # Children count
        ("pointCount", c_uint16),  # number of points at this node
    ]
    _array = (c_uint16 * 0)()

    @property
    def max_elements(self):
        return 128

    @property
    def default_chid(self) -> int:
        return CBSpecialChan.CONFIGURATION

    @property
    def default_type(self):
        return CBPacketType.VIDEOTRACKSET

    @property
    def sizes(self) -> list[int]:
        # Convert coords from uint16 to half as many uint32
        # TODO: Use numpy from buffer
        return struct.unpack(
            f"<{len(self.coords)//2}L",
            struct.pack(f"<{len(self.coords)}H", self._array),
        )

    @sizes.setter
    def sizes(self, insizes: list[int]):
        n_elems = len(insizes)
        assert n_elems <= (self.max_elements // 2)
        # TODO: Use numpy buffer
        self.coords = struct.unpack(
            f"<{len(insizes)*2}H", struct.pack(f"<{len(insizes)}L", insizes)
        )

    @property
    def coords(self) -> np.ndarray:
        return self.data

    @coords.setter
    def coords(self, incoords: numpy.typing.ArrayLike):
        self.data = incoords


class CBPacketLog(CBPacketVarLen):
    _fields_ = [
        ("header", CBPacketHeader),
        ("mode", c_uint16),  # cbLOG_MODE_*
        ("name", c_char * 16),  # Logger source name (Computer name, Plugin name, ...)
        ("desc", c_char * 128),  # description of the change
    ]
    _array = (c_char * 0)()  # For `desc` field: description of the change

    @property
    def default_type(self):
        return CBPacketType.LOGSET

    @property
    def default_chid(self) -> int:
        return CBSpecialChan.CONFIGURATION

    @property
    def max_elements(self):
        return 128  # cbMAX_LOG

    @property
    def desc(self) -> str:
        return self._array[: self.max_elements].decode("utf-8")

    @desc.setter
    def desc(self, indesc: str):
        assert len(indesc) <= self.max_elements
        self._array = (self._array._type_ * len(indesc))()
        self._array[: len(indesc)] = indesc.encode("utf-8")


class CBPacketVideoSynch(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("split", c_uint16),  # file split number of the video file
        ("frame", c_uint32),  # frame number in last video
        ("etime", c_uint32),  # capture elapsed time (in milliseconds)
        ("id", c_uint16),  # video source id
    ]

    @property
    def default_type(self):
        return CBPacketType.VIDEOSYNCHSET


class CBPacketGyro(CBPacketConfigFixed):
    _fields_ = [
        ("header", CBPacketHeader),
        ("gyroscope", c_uint8 * 4),
        ("accelerometer", c_uint8 * 4),
        ("magnetometer", c_uint8 * 4),
        ("temperature", c_uint16),
        ("reserved", c_uint16),
    ]


class CBPacketSSModelAll(CBPacketGeneric):
    pass


class CBPacketSSDetect(CBPacketGeneric):
    pass


class CBPacketSSArtifReject(CBPacketGeneric):
    pass


class CBPacketSSNoiseBoundary(CBPacketGeneric):
    pass


class CBPacketSSStatistics(CBPacketGeneric):
    pass


class CBPacketSSStatus(CBPacketGeneric):
    pass


def register_pktcls_with_factory(packet_factory):
    packet_factory.register_pktcls_by_channel_type(
        CBChannelType.FrontEnd, CBPacketSpike
    )
    packet_factory.register_pktcls_by_channel_type(CBChannelType.Group, CBPacketGroup)
    packet_factory.register_fallback_packet_class(CBPacketGeneric)
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.REPCONFIGALL], CBPacketGeneric
    )
    packet_factory.register_pktcls_by_channel_type(CBChannelType.DigitalIn, CBPacketDIn)
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SYSHEARTBEAT], CBPacketHeartBeat
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SET_DOUTSET, CBPacketType.SET_DOUTREP], CBPacketSetDOut
    )
    packet_factory.register_pktcls_by_header_types(
        [
            CBPacketType.SYSREP,
            CBPacketType.SYSREPSPKLEN,
            CBPacketType.SYSREPRUNLEV,
            CBPacketType.SYSSET,
            CBPacketType.SYSSETSPKLEN,
            CBPacketType.SYSSETRUNLEV,
        ],
        CBPacketSysInfo,
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.GROUPREP, CBPacketType.GROUPSET], CBPacketGroupInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.FILTREP, CBPacketType.FILTSET], CBPacketGroupInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.PROCREP], CBPacketProcInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.BANKREP], CBPacketBankInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.COMMENTREP, CBPacketType.COMMENTSET], CBPacketComment
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.CHANREP, CBPacketType.CHANSET], CBPacketChanInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.REPNTRODEINFO, CBPacketType.SETNTRODEINFO], CBPacketNTrodeInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.ADAPTFILTREP, CBPacketType.ADAPTFILTSET], CBPacketAdaptFiltInfo
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.LOGSET, CBPacketType.LOGREP], CBPacketLog
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SYSPROTOCOLMONITOR], CBPacketSysProtocolMonitor
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.REFELECFILTREP, CBPacketType.REFELECFILTSET],
        CBPacketRefElecFiltInfo,
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.LNCREP, CBPacketType.LNCSET], CBPacketLNC
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.REPFILECFG, CBPacketType.SETFILECFG], CBPacketFileCFG
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.VIDEOTRACKREP, CBPacketType.VIDEOTRACKSET], CBPacketVideoTrack
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.VIDEOSYNCHREP, CBPacketType.VIDEOSYNCHSET], CBPacketVideoSynch
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.NPLAYSET, CBPacketType.NPLAYREP], CBPacketNPlay
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_MODELALLREP, CBPacketType.SS_MODELALLSET], CBPacketSSModelAll
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_DETECTREP, CBPacketType.SS_DETECTSET], CBPacketSSDetect
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_ARTIF_REJECTREP, CBPacketType.SS_ARTIF_REJECTSET],
        CBPacketSSArtifReject,
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_NOISE_BOUNDARYREP, CBPacketType.SS_NOISE_BOUNDARYSET],
        CBPacketSSNoiseBoundary,
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_STATISTICSREP, CBPacketType.SS_STATISTICSSET],
        CBPacketSSStatistics,
    )
    packet_factory.register_pktcls_by_header_types(
        [CBPacketType.SS_STATUSREP, CBPacketType.SS_STATUSSET], CBPacketSSStatus
    )
