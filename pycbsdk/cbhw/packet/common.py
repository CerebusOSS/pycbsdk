from ctypes import *
from enum import IntEnum
from .. import config


PKT_MAX_SIZE = 1024  # bytes


class CBPacketType(IntEnum):
    # Note: Protocol >= 4.1 uses 16-bit types, so it might be necessary to prepend these with 0x00NN instead of 0xNN
    SYSHEARTBEAT = 0x00
    SYSPROTOCOLMONITOR = 0x01
    REPCONFIGALL = 0x08
    REQCONFIGALL = 0x88
    SYSREP = 0x10
    SYSSET = 0x90
    SYSREPSPKLEN = 0x11
    SYSSETSPKLEN = 0x91
    SYSREPRUNLEV = 0x12
    SYSSETRUNLEV = 0x92
    SYSREPTRANSPORT = 0x13
    SYSSETTRANSPORT = 0x93
    PROCREP = 0x21
    BANKREP = 0x22
    FILTREP = 0x23
    FILTSET = 0xA3
    CHANRESETREP = 0x24
    CHANRESET = 0xA4
    ADAPTFILTREP = 0x25
    ADAPTFILTSET = 0xA5
    REFELECFILTREP = 0x26
    REFELECFILTSET = 0xA6
    REPNTRODEINFO = 0x27
    SETNTRODEINFO = 0xA7
    LNCREP = 0x28
    LNCSET = 0xA8
    VIDEOSYNCHREP = 0x29
    VIDEOSYNCHSET = 0xA9
    GROUPREP = 0x30
    GROUPSET = 0xB0
    COMMENTREP = 0x31
    COMMENTSET = 0xB1
    NMREP = 0x32
    NMSET = 0xB2
    WAVEFORMREP = 0x33
    WAVEFORMSET = 0xB3
    STIMULATIONREP = 0x34
    STIMULATIONSET = 0xB4
    TRANSPORTREP = 0x35
    TRANSPORTSET = 0xB5
    CHANREP = 0x40
    CHANSET = 0xC0
    CHANREPLABEL = 0x41
    CHANSETLABEL = 0xC1
    CHANREPSCALE = 0x42
    CHANSETSCALE = 0xC2
    CHANREPDOUT = 0x43
    CHANSETDOUT = 0xC3
    CHANREPDINP = 0x44
    CHANSETDINP = 0xC4
    CHANREPAOUT = 0x45
    CHANSETAOUT = 0xC5
    CHANREPDISP = 0x46
    CHANSETDISP = 0xC6
    CHANREPAINP = 0x47
    CHANSETAINP = 0xC7
    CHANREPSMP = 0x48
    CHANSETSMP = 0xC8
    CHANREPSPK = 0x49
    CHANSETSPK = 0xC9
    CHANREPSPKTHR = 0x4A
    CHANSETSPKTHR = 0xCA
    CHANREPSPKHPS = 0x4B
    CHANSETSPKHPS = 0xCB
    CHANREPUNITOVERRIDES = 0x4C
    CHANSETUNITOVERRIDES = 0xCC
    CHANREPNTRODEGROUP = 0x4D
    CHANSETNTRODEGROUP = 0xCD
    CHANREPREJECTAMPLITUDE = 0x4E
    CHANSETREJECTAMPLITUDE = 0xCE
    CHANREPAUTOTHRESHOLD = 0x4F
    CHANSETAUTOTHRESHOLD = 0xCF
    SS_MODELALLREP = 0x50
    SS_MODELALLSET = 0xD0
    SS_MODELREP = 0x51
    SS_MODELSET = 0xD1
    SS_DETECTREP = 0x52
    SS_DETECTSET = 0xD2
    SS_ARTIF_REJECTREP = 0x53
    SS_ARTIF_REJECTSET = 0xD3
    SS_NOISE_BOUNDARYREP = 0x54
    SS_NOISE_BOUNDARYSET = 0xD4
    SS_STATISTICSREP = 0x55
    SS_STATISTICSSET = 0xD5
    SS_STATUSREP = 0x57
    SS_STATUSSET = 0xD7
    NPLAYREP = 0x5C
    NPLAYSET = 0xDC
    SET_DOUTREP = 0x5D
    SET_DOUTSET = 0xDD
    TRIGGERREP = 0x5E
    TRIGGERSET = 0xDE
    VIDEOTRACKREP = 0x5F
    VIDEOTRACKSET = 0xDF
    REPFILECFG = 0x61
    SETFILECFG = 0xE1
    LOGREP = 0x63
    LOGSET = 0xE3
    REPPATIENTINFO = 0x64
    SETPATIENTINFO = 0xE4
    REPIMPEDANCE = 0x65
    SETIMPEDANCE = 0xE5
    REPINITIMPEDANCE = 0x66
    SETINITIMPEDANCE = 0xE6
    REPPOLL = 0x67
    SETPOLL = 0xE7
    REPMAPFILE = 0x68
    SETMAPFILE = 0xE8
    UPDATEREP = 0x71
    UPDATESET = 0xF1
    PREVSETLNC = 0x81
    PREVREPLNC = 0x01  # Duplicate?!
    PREVSETSTREAM = 0x82
    PREVREPSTREAM = 0x02
    PREVSET = 0x83
    PREVREP = 0x03


class CBChannelType(IntEnum):
    Any = -1  # Any / Unknown
    Group = 0  # Used for non-config packets with chid==0, i.e. sample group (multichannel) packets
    FrontEnd = 1
    AnalogIn = 2
    DigitalIn = 3
    DigitalOut = 4
    Serial = 5
    Audio = 6


class CBSpecialChan(IntEnum):
    GROUP = 0x0000
    CONFIGURATION = 0x8000


class CBTransport(IntEnum):
    UDP = 0x0000
    TCP = 0x0001
    LSL = 0x0004
    USB = 0x0008
    SERIAL = 0x000F
    ALL = 0xFFFF


class CBScaling(Structure):
    _pack_ = 1
    _fields_ = [
        ("digmin", c_int16),
        ("digmax", c_int16),
        ("anamin", c_int32),
        ("anamax", c_int32),
        ("anagain", c_int32),
        ("anaunit", c_char * 8),
    ]


class CBFiltDesc(Structure):
    _pack_ = 1
    _fields_ = [
        ("label", c_char * 16),
        ("hpfreq", c_uint32),
        ("hporder", c_uint32),
        ("hptype", c_uint32),
        ("lpfreq", c_uint32),
        ("lporder", c_uint32),
        ("lptype", c_uint32),
    ]


class CBManualUnitMapping(Structure):
    _pack_ = 1
    _fields_ = [
        ("nOverride", c_int16),
        ("afOrigin", c_int16 * 3),
        ("afShape", c_int16 * 3 * 3),
        ("aPhi", c_int16),
        ("bValid", c_uint32),  # is this unit in use at this time?
    ]


class CBHoop(Structure):
    _pack_ = 1
    _fields_ = [
        ("valid", c_uint16),  # 0=undefined, 1 for valid
        ("time", c_int16),  # time offset into spike window
        ("min", c_int16),  # minimum value for the hoop window
        ("max", c_int16),  # maximum value for the hoop window
    ]


class CBChanLowHigh(Structure):
    _fields_ = [
        ("lowsamples", c_uint16),  # ??
        ("highsamples", c_uint16),  # ??
        ("offset", c_int32),  # ??
    ]


class CBChanMonitor(Structure):
    _fields_ = [
        ("monsource", c_uint32),  # address of channel to monitor
        ("outvalue", c_int32),  # output value
    ]


class CBChanInfoUnion(Union):
    _fields_ = [("a", CBChanMonitor), ("b", CBChanLowHigh)]


class CBNPlayMode(IntEnum):
    NONE = 0  # no command (parameters)
    PAUSE = 1  # PC->NPLAY pause if "val" is non-zero, un-pause otherwise
    SEEK = 2  # PC->NPLAY seek to time "val"
    CONFIG = 3  # PC<->NPLAY request full config
    OPEN = 4  # PC->NPLAY open new file in "val" for playback
    PATH = 5  # PC->NPLAY use the directory path in fname
    CONFIGMAIN = 6  # PC<->NPLAY request main config packet
    STEP = 7  # PC<->NPLAY run "val" procTime steps and pause, then send cbNPLAY_FLAG_STEPPED
    SINGLE = 8  # PC->NPLAY single mode if "val" is non-zero, wrap otherwise
    RESET = 9  # PC->NPLAY reset nPlay
    NEVRESORT = 10  # PC->NPLAY resort NEV if "val" is non-zero, do not if otherwise
    AUDIO_CMD = 11  # PC->NPLAY perform audio command in "val" (cbAUDIO_CMD_*), with option "opt"


class CBNPlayFlag(IntEnum):
    NONE = 0  # no flag
    CONF = 0x01  # NPLAY->PC config packet ("val" is "fname" file index)
    MAIN = 0x02 | 0x01  # NPLAY->PC main config packet ("val" is file version)
    DONE = 0x02  # NPLAY->PC step command done
