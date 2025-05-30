"""
This module handles the actual communication.

The client application is expected to use the API (`cbsdk`) to get an opaque
object representing the device, then to call `cbsdk.connect(device_obj)`.

Calling `connect` will initiate a cascade that will eventually lead to 2 async chains.
First, a thread is created. This thread launches an infinite async chain to receive and process datagrams. Thus,
the thread is necessary because otherwise `connect` would be a blocking call.
The thread creates its own sub-thread, within which a sender async chain is started.

main-thread --> client calls cbsdk.connect(device_obj)
secondary thread --> Sets up a datagram protocol, creates tertiary thread (passing the transport from protocol),
    and starts receiver async chain in secondary thread.
tertiary thread --> uses the shared transport and starts sender async chain

As the main-thread is not blocked, the client is then free to call other `cbsdk` methods,
including configuring the device, checking its status, and registering callbacks.

Note that callbacks happen in the secondary thread (via datagram receiver async chain). Therefore, if a callback
is expected to access a client object that might also be accessed via the main thread, appropriate thread-safe
synchronization primitives should be used.

"""

import copy
from ctypes import Structure, create_string_buffer
import logging
import socket
from collections.abc import Callable
from enum import IntEnum, IntFlag
from typing import Optional
import struct
import threading
import time

# NOTE: We cannot import from .packet.packets until after config.protocol is set;
# other .packet.{submodules} are OK.
from pycbsdk.cbhw.device.base import DeviceInterface
from pycbsdk.cbhw.handler import PacketHandlerThread
from pycbsdk.cbhw.io.datagram import CerebusDatagramThread
from pycbsdk.cbhw.packet.common import (
    CBChannelType,
    CBPacketType,
    CBNPlayMode,
    CBNPlayFlag,
    CBSpecialChan,
    CBHoop,
    MAX_UNITS,
    MAX_HOOPS,
)
from pycbsdk.cbhw.params import Params
from pycbsdk.cbhw.consts import CBError


__all__ = ["SpikeEvent", "NSPDevice", "CBRunLevel"]


# globals
logger = logging.getLogger(__name__)
g_debug_unhandled_packets = set()


# region Consts
cbNUM_FE_CHANS = 256
cbNUM_ANAIN_CHANS = 16
cbNUM_ANALOG_CHANS = cbNUM_FE_CHANS + cbNUM_ANAIN_CHANS
cbNUM_ANAOUT_CHANS = 4
cbNUM_AUDOUT_CHANS = 2
cbNUM_ANALOGOUT_CHANS = cbNUM_ANAOUT_CHANS + cbNUM_AUDOUT_CHANS
cbNUM_DIGIN_CHANS = 1
cbNUM_SERIAL_CHANS = 1
cbNUM_DIGOUT_CHANS = 4
# endregion
GET_CONFIG_TIMEOUT = 2.0


# region Enums
class CBRunLevel(IntEnum):
    STARTUP = 10
    HARDRESET = 20
    STANDBY = 30
    RESET = 40
    RUNNING = 50
    STRESSED = 60
    ERROR = 70
    SHUTDOWN = 80


class CBTransport(IntFlag):
    CHECK = 0
    UDP = 0x0001
    TCP = 0x0002
    LSL = 0x0004
    USB = 0x0008
    SERIAL = 0x000F


class CBChanCaps(IntEnum):
    exists = 0x00000001  # Channel id is allocated
    connected = 0x00000002  # Channel is connected and mapped and ready to use
    isolated = 0x00000004  # Channel is electrically isolated
    ainp = 0x00000100  # Channel has analog input capabilities
    aout = 0x00000200  # Channel has analog output capabilities
    dinp = 0x00000400  # Channel has digital input capabilities
    dout = 0x00000800  # Channel has digital output capabilities
    gyro = 0x00001000  # Channel has gyroscope/accelerometer/magnetometer/temperature capabilities


class CBAnaInpCaps(IntEnum):  # TODO: Probably better captured by Flag class
    rawpreview = 0x00000001  # Generate scrolling preview data for the raw channel
    lnc = 0x00000002  # Line Noise Cancellation
    lncpreview = 0x00000004  # Retrieve the LNC correction waveform
    smpstream = 0x00000010  # stream the analog input stream directly to disk
    smpfilter = 0x00000020  # Digitally filter the analog input stream
    rawstream = 0x00000040  # Raw data stream available
    spkstream = 0x00000100  # Spike Stream is available
    spkfilter = 0x00000200  # Selectable Filters
    spkpreview = 0x00000400  # Generate scrolling preview of the spike channel
    spkproc = 0x00000800  # Channel is able to do online spike processing
    offset_correct_cap = 0x00001000  # Offset correction mode (0-disabled 1-enabled)


class CBAnaInpOpts(IntEnum):
    lnc_off = 0x00000000
    lnc_runhard = 0x00000001
    lnc_runsoft = 0x00000002
    lnc_hold = 0x00000004
    lnc_mask = 0x00000007  # Mask for LNC Flags
    refelec_lfpspk = 0x00000010
    refelec_spk = 0x00000020
    refelec_mask = 0x00000030
    refelec_rawstream = 0x00000040
    refelec_offsetcorrect = 0x00000100


class CBAOutOpts(IntEnum):
    AUDIO = 0x00000001
    SCALE = 0x00000002
    TRACK = 0x00000004
    STATIC = 0x00000008
    MONITOR_RAW = 0x00000010
    MONITOR_LNC = 0x00000020
    MONITOR_SMP = 0x00000040
    MONITOR_SPK = 0x00000080
    STIMULATE = 0x00000100
    WAVEFORM = 0x00000200
    EXTENSION = 0x00000400


class CBDigInpCaps(IntEnum):  # TODO: Probably better captured by Flag class
    serialmask = 0x000000FF  # Bit mask used to detect RS232 Serial Baud Rates
    baud2400 = 0x00000001  # RS232 Serial Port operates at 2400   (n-8-1)
    baud9600 = 0x00000002  # RS232 Serial Port operates at 9600   (n-8-1)
    baud19200 = 0x00000004  # RS232 Serial Port operates at 19200  (n-8-1)
    baud38400 = 0x00000008  # RS232 Serial Port operates at 38400  (n-8-1)
    baud57600 = 0x00000010  # RS232 Serial Port operates at 57600  (n-8-1)
    baud115200 = 0x00000020  # RS232 Serial Port operates at 115200 (n-8-1)
    in1bit = 0x00000100  # Port has a single input bit (eg single BNC input)
    in8bit = 0x00000200  # Port has 8 input bits
    in16bit = 0x00000400  # Port has 16 input bits
    in32bit = 0x00000800  # Port has 32 input bits
    inanybit = 0x00001000  # Capture the port value when any bit changes.
    wrdstrb = 0x00002000  # Capture the port when a word-write line is strobed
    pktchar = 0x00004000  # Capture packets using an End of Packet Character
    pktstrb = 0x00008000  # Capture packets using an End of Packet Logic Input
    monitor = 0x00010000  # Port controls other ports or system events
    redge = (
        0x00020000  # Capture the port value when any bit changes lo-2-hi (rising edge)
    )
    fedge = (
        0x00040000  # Capture the port value when any bit changes hi-2-lo (falling edge)
    )
    strbany = 0x00080000  # Capture packets using 8-bit strobe/8-bit any Input
    strbris = 0x00100000  # Capture packets using 8-bit strobe/8-bit rising edge Input
    strbfal = 0x00200000  # Capture packets using 8-bit strobe/8-bit falling edge Input
    mask = (
        inanybit
        | wrdstrb
        | pktchar
        | pktstrb
        | monitor
        | redge
        | fedge
        | strbany
        | strbris
    )


class CBAnaOutCaps(IntEnum):  # TODO: Probably better captured by Flag class.
    audio = 0x00000001  # Channel is physically optimized for audio output
    scale = 0x00000002  # Output a static value
    track = 0x00000004  # Output a static value
    static = 0x00000008  # Output a static value
    monitorraw = 0x00000010  # Monitor an analog signal line - RAW data
    monitorlnc = 0x00000020  # Monitor an analog signal line - Line Noise Cancelation
    monitorsmp = 0x00000040  # Monitor an analog signal line - Continuous
    monitorspk = 0x00000080  # Monitor an analog signal line - spike
    stimulate = 0x00000100  # Stimulation waveform functions are available.
    waveform = 0x00000200  # Custom Waveform
    extension = 0x00000400  # Output Waveform from Extension


class CBAInpSpk(IntFlag):
    EXTRACT = 0x00000001  # Time-stamp and packet to first superthreshold peak
    REJART = 0x00000002  # Reject around clipped signals on multiple channels
    REJCLIP = 0x00000004  # Reject clipped signals on the channel
    ALIGNPK = 0x00000008  #
    REJAMPL = 0x00000010  # Reject based on amplitude
    THRLEVEL = 0x00000100  # Analog level threshold detection
    THRENERGY = 0x00000200  # Energy threshold detection
    THRAUTO = 0x00000400  # Auto threshold detection
    SPREADSORT = 0x00001000  # Enable Auto spread Sorting
    CORRSORT = 0x00002000  # Enable Auto Histogram Correlation Sorting
    PEAKMAJSORT = 0x00004000  # Enable Auto Histogram Peak Major Sorting
    PEAKFISHSORT = 0x00008000  # Enable Auto Histogram Peak Fisher Sorting
    HOOPSORT = 0x00010000  # Enable Manual Hoop Sorting
    PCAMANSORT = 0x00020000  # Enable Manual PCA Sorting
    PCAKMEANSORT = 0x00040000  # Enable K-means PCA Sorting
    PCAEMSORT = 0x00080000  # Enable EM-clustering PCA Sorting
    PCADBSORT = 0x00100000  # Enable DBSCAN PCA Sorting
    NOSORT = 0x00000000  # No sorting
    AUTOSORT = (
        SPREADSORT | CORRSORT | PEAKMAJSORT | PEAKFISHSORT
    )  # old auto sorting methods
    PCAAUTOSORT = (
        PCAKMEANSORT | PCAEMSORT | PCADBSORT
    )  # All PCA sorting auto algorithms
    PCASORT = PCAMANSORT | PCAAUTOSORT  # All PCA sorting algorithms
    ALLSORT = AUTOSORT | HOOPSORT | PCASORT  # All sorting algorithms


class LNCRate:
    lnc_rates = {
        0: 0,
        1: 1000,
        10: 10000,
        30: 30000,
        60: 60000,
    }

    @staticmethod
    def GetLNCRate(key) -> int:
        try:
            return LNCRate.lnc_rates[key]
        except KeyError:
            print("Error with LNC rate key.")
            return 0


# endregion


# type aliases
SpikeEvent = tuple[int, int, int]  # proctime, channel_id, unit_id


def get_chantype_from_chaninfo(pkt) -> CBChannelType:
    if (CBChanCaps.isolated | CBChanCaps.ainp) == (
        pkt.chancaps & (CBChanCaps.isolated | CBChanCaps.ainp)
    ):
        return CBChannelType.FrontEnd
    elif (pkt.chancaps & CBChanCaps.ainp) and not (pkt.chancaps & CBChanCaps.isolated):
        return CBChannelType.AnalogIn
    elif pkt.chancaps & CBChanCaps.dinp:
        if pkt.dinpcaps & CBDigInpCaps.serialmask:
            return CBChannelType.Serial
        else:
            return CBChannelType.DigitalIn
    elif pkt.chancaps & CBChanCaps.dout:
        return CBChannelType.DigitalOut
    elif (pkt.chancaps & CBChanCaps.aout) and (pkt.aoutcaps & CBAnaOutCaps.audio):
        return CBChannelType.Audio


class NSPDevice(DeviceInterface):
    def __init__(self, params: Params, **kwargs):
        super().__init__(params, **kwargs)

        # State
        self._config["runlevel"] = CBRunLevel.STARTUP
        self._config["nplay"] = None
        self._config["transport"] = CBTransport.CHECK
        self.last_time = 1
        self._monitor_state["time"] = 1

        # Placeholders for IO
        self._sender_queue = None
        self._io_thread = None

        self._register_basic_callbacks()

        self._config_func_map = {
            "smpgroup": self._configure_channel_smpgroup,
            "smpfilter": self._configure_channel_smpfilter,
            "autothreshold": self._configure_channel_autothreshold,
            "label": self._configure_channel_label,
            "lnc": self._configure_channel_lnc,
            "lnc_rate": self._configure_channel_lnc_rate,
            "global_lnc": self._set_lnc_global_config,
            "dc_offset": self._configure_channel_dcoffset,
            "spkfilter": self._configure_channel_spkfilter,
            "spkthrlevel": self._configure_spk_threshold,
        }

        # Receives broadcast UDP (or unicast targeting the adapter at client_addr).
        self._local_addr = (
            socket.gethostbyname(self._params.client_addr),
            self._params.client_port,
        )
        # Send to a specific address
        self._device_addr = (
            socket.gethostbyname(self._params.inst_addr),
            self._params.inst_port,
        )

        # Start the packet handler thread. We don't expect it to receive any packets until `.connect()` is called.
        self._pkt_handler_thread = PacketHandlerThread(self)
        self._pkt_handler_thread.start()

    @property
    def device_addr(self) -> tuple[str, int]:
        return self._device_addr

    # region BasicCallbacks
    def _register_basic_callbacks(self):
        self.register_config_callback(CBPacketType.REPCONFIGALL, self._handle_configall)
        self.register_config_callback(CBPacketType.SYSREP, self._handle_sysrep)
        self.register_config_callback(CBPacketType.SYSREPRUNLEV, self._handle_sysrep)
        self.register_config_callback(CBPacketType.SYSREPTRANSPORT, self._handle_sysrep)
        self.register_config_callback(CBPacketType.CHANREP, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPSMP, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPSPKHPS, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPSPK, self._handle_chaninfo)
        self.register_config_callback(
            CBPacketType.CHANREPAUTOTHRESHOLD, self._handle_chaninfo
        )
        self.register_config_callback(
            CBPacketType.CHANREPREJECTAMPLITUDE, self._handle_chaninfo
        )
        self.register_config_callback(CBPacketType.CHANREPAOUT, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPSCALE, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPDINP, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPDOUT, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPLABEL, self._handle_chaninfo)

        self.register_config_callback(CBPacketType.CHANREPAINP, self._handle_chaninfo)
        self.register_config_callback(CBPacketType.CHANREPSPKTHR, self._handle_chaninfo)
        self.register_config_callback(
            CBPacketType.CHANREPNTRODEGROUP, self._handle_chaninfo
        )
        self.register_config_callback(CBPacketType.CHANREPDISP, self._handle_chaninfo)
        self.register_config_callback(
            CBPacketType.CHANREPUNITOVERRIDES, self._handle_chaninfo
        )

        self.register_config_callback(CBPacketType.GROUPREP, self._handle_groupinfo)
        self.register_config_callback(CBPacketType.PROCREP, self._handle_procinfo)
        self.register_config_callback(CBPacketType.NPLAYREP, self._handle_nplay)
        self.register_config_callback(
            CBPacketType.SYSPROTOCOLMONITOR, self._handle_procmon
        )
        self.register_config_callback(CBPacketType.LOGREP, self._handle_log)
        self.register_config_callback(CBPacketType.COMMENTREP, self._handle_comment)
        # Register the _black_hole (do nothing) callback for packets we are aware of but do not handle yet
        self.register_config_callback(CBPacketType.SYSHEARTBEAT, self._black_hole)
        self.register_config_callback(CBPacketType.SS_MODELREP, self._black_hole)
        self.register_config_callback(CBPacketType.SS_DETECTREP, self._black_hole)
        self.register_config_callback(CBPacketType.ADAPTFILTREP, self._black_hole)
        self.register_config_callback(CBPacketType.SS_ARTIF_REJECTREP, self._black_hole)
        self.register_config_callback(CBPacketType.LNCREP, self._black_hole)
        self.register_config_callback(
            CBPacketType.SS_NOISE_BOUNDARYREP, self._black_hole
        )
        self.register_config_callback(CBPacketType.SS_STATISTICSREP, self._black_hole)
        self.register_config_callback(CBPacketType.REPFILECFG, self._black_hole)
        self.register_config_callback(CBPacketType.SS_STATUSREP, self._black_hole)
        self.register_config_callback(CBPacketType.FILTREP, self._black_hole)
        self.register_config_callback(CBPacketType.BANKREP, self._black_hole)
        self.register_config_callback(CBPacketType.REPNTRODEINFO, self._black_hole)
        self.register_config_callback(CBPacketType.REFELECFILTREP, self._black_hole)

    def _handle_sysrep(self, pkt):
        logger.info(
            f"SYSREP --\trunlevel:{CBRunLevel(pkt.runlevel)!r}\tproctime:{pkt.header.time}"
        )
        b_general = pkt.header.type == CBPacketType.SYSREP
        if (b_general or pkt.header.type == CBPacketType.SYSREPTRANSPORT) and hasattr(
            pkt, "transport"
        ):
            # This feature is only available in Chad's beta nplayserver.
            self._config["transport"] = pkt.transport  # bitwise or'd flags
        if b_general or pkt.header.type == CBPacketType.SYSREPRUNLEV:
            self._config["runlevel"] = CBRunLevel(pkt.runlevel)
            self._config["sysfreq"] = pkt.sysfreq
            self._config["instrument"] = pkt.header.instrument
        self._config_events["sysrep"].set()
        if b_general or pkt.header.type == CBPacketType.SYSREPRUNLEV:
            if self._config["runlevel"] == CBRunLevel.STANDBY:
                self._config_events["runlevel_standby"].set()
            elif self._config["runlevel"] == CBRunLevel.RUNNING:
                self._config_events["runlevel_running"].set()

    def _handle_chaninfo(self, pkt):
        # If this config packet is limited in scope then it might have some garbage data in its out-of-scope payload.
        # We should update our config, but only the parts that this REP packet is scoped to.
        if (pkt.header.instrument != self._config["instrument"]) or (
            pkt.chan > self._config["proc_chans"]
        ):
            # Drop channels that do not belong to this instrument
            pass
        elif pkt.header.type in [CBPacketType.CHANREP]:
            # Full scope; overwrite our config.
            self._config["channel_infos"][pkt.chan] = copy.copy(pkt)
            self._config["channel_types"][pkt.chan] = get_chantype_from_chaninfo(pkt)
        else:
            # Note: Some types have overlapping fields.
            if pkt.header.type == CBPacketType.CHANREPAINP:
                self._config["channel_infos"][pkt.chan].ainpopts = pkt.ainpopts
                self._config["channel_infos"][pkt.chan].lncrate = pkt.lncrate
                self._config["channel_infos"][pkt.chan].refelecchan = pkt.refelecchan
            elif pkt.header.type == CBPacketType.CHANREPSPK:
                self._config["channel_infos"][pkt.chan].spkopts = pkt.spkopts
                self._config["channel_infos"][pkt.chan].spkfilter = pkt.spkfilter
            elif pkt.header.type in [CBPacketType.CHANREPREJECTAMPLITUDE]:
                self._config["channel_infos"][pkt.chan].spkopts = pkt.spkopts
                self._config["channel_infos"][pkt.chan].amplrejpos = pkt.amplrejpos
                self._config["channel_infos"][pkt.chan].amplrejneg = pkt.amplrejneg
            elif pkt.header.type == CBPacketType.CHANREPAUTOTHRESHOLD:
                self._config["channel_infos"][pkt.chan].spkopts = pkt.spkopts
            elif pkt.header.type == CBPacketType.CHANREPSMP:
                self._config["channel_infos"][pkt.chan].smpfilter = pkt.smpfilter
                self._config["channel_infos"][pkt.chan].smpgroup = pkt.smpgroup
            elif pkt.header.type == CBPacketType.CHANREPSPKHPS:
                self._config["channel_infos"][pkt.chan].spkhoops = pkt.spkhoops
                # TODO: .unitmapping[n].bValid = pkt.spkhoops[n][0].valid ??
            elif pkt.header.type == CBPacketType.CHANREPAOUT:
                self._config["channel_infos"][pkt.chan].aoutopts = pkt.aoutopts
                # self._config["channel_infos"][pkt.chan].union.a.moninst = pkt.moninst
                # self._config["channel_infos"][pkt.chan].union.a.monchan = pkt.monchan
            elif pkt.header.type == CBPacketType.CHANREPSCALE:
                self._config["channel_infos"][pkt.chan].scalin = pkt.scalin
                self._config["channel_infos"][pkt.chan].scalout = pkt.scalout
            elif pkt.header.type == CBPacketType.CHANREPDINP:
                # TODO: NOTE: Need extra check if this is for serial or digital?
                self._config["channel_infos"][pkt.chan].dinpopts = pkt.dinpopts
                self._config["channel_infos"][pkt.chan].eopchar = pkt.eopchar
            elif pkt.header.type == CBPacketType.CHANREPDOUT:
                self._config["channel_infos"][pkt.chan].doutopts = pkt.doutopts
                self._config["channel_infos"][pkt.chan].doutcaps = pkt.doutcaps
                # TODO: .moninst, .monchan, .outvalue, more..., from union?
            elif pkt.header.type == CBPacketType.CHANREPLABEL:
                self._config["channel_infos"][pkt.chan].label = pkt.label
                self._config["channel_infos"][pkt.chan].userflags = pkt.userflags
            elif pkt.header.type in [
                CBPacketType.CHANSETSPKTHR,
                CBPacketType.CHANREPSPKTHR,
            ]:
                self._config["channel_infos"][pkt.chan].spkthrlevel = pkt.spkthrlevel
            elif pkt.header.type == CBPacketType.CHANREPNTRODEGROUP:
                # TODO: from use pkt.spkgroup
                pass
            elif pkt.header.type == CBPacketType.CHANREPDISP:
                # TODO: Use .smpdispmin, .smpdispmax, .spkdispmax, .lncdispmax
                pass
            elif pkt.header.type == CBPacketType.CHANREPUNITOVERRIDES:
                # TODO: Use .unitmapping
                pass
            else:
                pass
        # print(f"handled chaninfo {pkt.chan} of type {hex(pkt.header.type)}")
        self._config_events["chaninfo"].set()

    def _handle_groupinfo(self, pkt):
        if pkt.length > 0:
            chan_list = set(pkt.chan_list.flatten())
        else:
            chan_list = set()
        self._config["group_infos"][pkt.group] = chan_list
        self._config["group_nchans"][pkt.group] = len(chan_list)

    def _handle_configall(self, pkt):
        if pkt.header.dlen > 0:
            logger.warning("REPCONFIGALL has unexpected payload")

    def _handle_procinfo(self, pkt):
        vmin, vmaj = struct.unpack("HH", struct.pack("I", pkt.version))
        prot_str = f"{vmaj}.{vmin}"
        logger.info(f"Protocol version {prot_str}")
        self._config["proc_chans"] = pkt.chancount
        # config.protocol = prot_str  # Too late; we already loaded our factory if we got this far.

    def _handle_nplay(self, pkt):
        self._config["nplay"] = pkt

    def _handle_procmon(self, pkt):
        arrival_time = time.time()
        # Note: There's about 0.57 msec from when procmon is sent to when it is received.
        # so we could make sys_time = arrival_time - 570_000e-9
        update_interval = max(pkt.header.time - self._monitor_state["time"], 1)
        pkt_delta = self.pkts_received - self._monitor_state["pkts_received"]

        v_int = [int(_) for _ in self._params.protocol.split(".")]
        has_counter = v_int[0] > 4 or (v_int[0] == 4 and v_int[1] > 1)
        if has_counter and pkt.counter > (self._monitor_state["counter"] + 1):
            logger.warning("Missing SYSPROTOCOLMONITOR packets.")

        logger.info(
            f"SYSPROTOCOLMONITOR:\tpkts_received - {self.pkts_received}"
            f";\ttime - {pkt.header.time}"
            f";\tcounter - {pkt.counter if has_counter else 'N/A'}"
            f";\tdelta - {pkt_delta}"
            f";\tsent - {pkt.sentpkts}"
            f";\trate (pkt/samp) - {pkt_delta / update_interval}"
        )
        self._monitor_state = {
            "counter": pkt.counter if has_counter else -1,
            "time": pkt.header.time,
            "pkts_received": self.pkts_received,
            "sys_time": arrival_time,
        }

    def _handle_log(self, pkt):
        log_lvls = {0: logging.INFO, 1: logging.CRITICAL, 5: logging.ERROR}
        log_lvl = log_lvls.get(pkt.mode, logging.INFO)
        logger.log(log_lvl, f"Log from {pkt.name}:\t{pkt.desc}")

    def _handle_comment(self, pkt):
        # Note: Though we might receive a comment in response to one we just sent,
        #  we do not use events for comments because timing is not critical and
        #  there is no need to wait for a response when firing off a comment.
        if hasattr(pkt, "timeStarted"):
            logger.debug(f"At {pkt.timeStarted}, received comment:\t{pkt.comment}")
        else:
            logger.debug(f"Received comment:\t{pkt.comment}")

    def _black_hole(self, pkt):
        _old = len(g_debug_unhandled_packets)
        g_debug_unhandled_packets.add(pkt.header.type)
        if len(g_debug_unhandled_packets) > _old:
            logger.debug(
                f"Ignoring {type(pkt)} packets with type {hex(pkt.header.type)}"
            )

    # endregion

    # region AdvancedCallbacks
    def register_group_callback(
        self, group: int, callback: Callable[[Structure], None]
    ):
        # TODO: Make this thread safe.
        self.group_callbacks[group].append(callback)

    def unregister_group_callback(
        self, group: int, callback: Callable[[Structure], None]
    ) -> int:
        if callback in self.group_callbacks[group]:
            self.group_callbacks[group].remove(callback)
            return 0
        else:
            return -1

    def register_event_callback(
        self, chan_type: CBChannelType, callback: Callable[[Structure], None]
    ):
        """
        :param chan_type: The type of channel this event is associated with. See CBChannelType for more info.
        :param callback:
        """
        # TODO: Make this thread safe.
        self.event_callbacks[chan_type].append(callback)

    def unregister_event_callback(
        self, chan_type: CBChannelType, callback: Callable[[Structure], None]
    ) -> int:
        if callback in self.event_callbacks[chan_type]:
            self.event_callbacks[chan_type].remove(callback)
            return 0
        else:
            return -1

    def register_config_callback(
        self, pkt_type: CBPacketType, callback: Callable[[Structure], None]
    ):
        # TODO: Make this thread safe.
        self.config_callbacks[pkt_type].append(callback)

    def unregister_config_callback(
        self, pkt_type: CBPacketType, callback: Callable[[Structure], None]
    ) -> int:
        if callback in self.config_callbacks[pkt_type]:
            self.config_callbacks[pkt_type].remove(callback)
            return 0
        else:
            return -1

    # endregion

    # region Configure
    def configure(self, cfg_name, cfg_value):
        print(f"TODO: set {cfg_name} to {cfg_value}")

    def _toggle_channel_ainp_flag(
        self, chid: int, flag: int, enable: bool, timeout: float = 0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETAINP
        pkt.ainpopts &= ~flag  # Always unset first
        pkt.ainpopts |= flag if enable else 0  # Then re-apply or not

        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.ainpopts != self._config["channel_infos"][chid].ainpopts:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_smpgroup(
        self, chid: int, attr_value: int, timeout: float = 0
    ):
        if attr_value in [0, 5]:
            # Disable raw when setting group to 0 or 5
            self._toggle_channel_ainp_flag(
                chid, CBAnaInpOpts.refelec_rawstream, False, timeout
            )
            time.sleep(0.005)
        elif attr_value == 6:
            # Enable raw. Note: We do not first check that 5 is not enabled.
            self._toggle_channel_ainp_flag(
                chid, CBAnaInpOpts.refelec_rawstream, True, timeout
            )
            time.sleep(0.005)

        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETSMP
        pkt.smpgroup = attr_value
        # safe lowpass digital filter for smpgroups 1-4. Otherwise, disable filter.
        pkt.smpfilter = {1: 5, 2: 6, 3: 7, 4: 10}.get(attr_value, 0)

        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if (pkt.smpgroup != self._config["channel_infos"][chid].smpgroup) or (
                pkt.smpfilter != self._config["channel_infos"][chid].smpfilter
            ):
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_autothreshold(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETAUTOTHRESHOLD
        # pkt.header.dlen = cbPKTDLEN_CHANINFOSHORT
        pkt.spkopts &= ~CBAInpSpk.THRAUTO.value
        pkt.spkopts |= CBAInpSpk.THRAUTO.value if attr_value else 0
        event = self._config_events["chaninfo"] if timeout > 0 else None
        self._send_packet(pkt=pkt, event=event, timeout=timeout)

    def _configure_channel_hoops(self, chid: int, attr_value: dict, timeout: float = 0):
        """
        Args:
            chid: 1-based channel index
            attr_value: a dictionary of dictionaries of dictionaries.
                The outer dictionary keys are the 1-based unit ids.
                The middle dictionary keys are the 1-based hoop ids.
                The inner dictionary has mandatory fields 'time', 'min', and 'max'
                    and optional field 'enabled' (or 'valid' is accepted).
                    All values are assumed integers.
                e.g. attr_value = {
                    1: {
                        1: {'time': 13, 'min': -975, 'max': -646, 'enabled': 1},
                        2: {'time': 6, 'min': 108, 'max': 342, 'enabled': 1}
                    },
                    2: {
                    ...
                    }, ...
                }
                This will set the first two hoops for unit-1.
        """
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETSPKHPS

        for unit_id, hoop_dicts in attr_value.items():
            if unit_id > MAX_UNITS:
                # TODO: Should these also check for negative index?
                raise IndexError(f"{unit_id} is greater than {MAX_UNITS}")
            for hoop_id, hoop in hoop_dicts.items():
                if hoop_id > MAX_HOOPS:
                    raise IndexError(f"{hoop_id} is greater than {MAX_HOOPS}")
                pkt.spkhoops[unit_id - 1][hoop_id - 1] = CBHoop(
                    valid=int(
                        hoop["enabled"] if "enabled" in hoop else hoop.get("valid", 1)
                    ),
                    time=int(hoop["time"]),
                    min=int(hoop["min"]),
                    max=int(hoop["max"]),
                )

        event = self._config_events["chaninfo"] if timeout > 0 else None
        self._send_packet(pkt=pkt, event=event, timeout=timeout)

    def _configure_channel_label(self, chid: int, attr_value: str, timeout: float = 0):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETLABEL
        pkt.label = bytes(create_string_buffer(attr_value.encode("utf-8"), 16))
        # TODO: pkt.userflags
        # TODO: pkt.position
        event = self._config_events["chaninfo"] if timeout > 0 else None
        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.label != self._config["channel_infos"][chid].label:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_lnc(self, chid: int, attr_value: int, timeout: float = 0):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETAINP
        pkt.ainpopts &= ~CBAnaInpOpts.lnc_mask
        if attr_value:
            pkt.ainpopts |= CBAnaInpOpts.lnc_runsoft

        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.ainpopts != self._config["channel_infos"][chid].ainpopts:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_lnc_rate(
        self, chid: int, attr_value: int, timeout: float
    ) -> None:
        pkt = copy.copy(self._config["channel_infos"][chid])

        pkt.lncrate = LNCRate.GetLNCRate(attr_value)
        pkt.header.type = CBPacketType.CHANSETAINP

        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.lncrate != self._config["channel_infos"][chid].lncrate:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _set_lnc_global_config(
        self, chid: int, attr_value: int = 60, timeout: float = 0
    ):
        pkt = self.packet_factory.make_packet(
            data=None,
            chid=CBSpecialChan.CONFIGURATION,
            pkt_type=CBPacketType.LNCSET,
        )

        pkt.lncFreq = attr_value
        pkt.lncRefChan = chid  # which channel do we look at as the ref for LNC?
        pkt.lncGlobalMode = 0  # Central sets this to zero, just doing the same here.
        #  What is the type of event this should be configure for?
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if (
                (pkt.lncFreq != self._config["channel_infos"][chid].lncFreq)
                or (pkt.lncRefChan != self._config["channel_infos"][chid].lncRefChan)
                or (
                    pkt.lncGlobalMode
                    != self._config["channel_infos"][chid].lncGlobalMode
                )
            ):
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_dcoffset(
        self, chid: int, attr_value: bool, timeout: float = 0.0
    ):
        self._toggle_channel_ainp_flag(
            chid=chid,
            flag=CBAnaInpOpts.refelec_offsetcorrect,
            enable=not not attr_value,
            timeout=timeout,
        )

    def _configure_channel_spkfilter(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.spkfilter = attr_value
        pkt.header.type = CBPacketType.CHANSETSPK
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.spkfilter != self._config["channel_infos"][chid].spkfilter:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_spk_threshold(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.spkthrlevel = attr_value
        pkt.header.type = CBPacketType.CHANSETSPKTHR

        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.spkthrlevel != self._config["channel_infos"][chid].spkthrlevel:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_analogout(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.aoutopts = attr_value
        pkt.header.type = CBPacketType.CHANSETAOUT
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.aoutopts != self._config["channel_infos"][chid].aoutopts:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_digital_input(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.dinpopts = attr_value
        pkt.header.type = CBPacketType.CHANSETDINP
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.dinpopts != self._config["channel_infos"][chid].dinpopts:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_digital_output(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.doutopts = attr_value
        pkt.header.type = CBPacketType.CHANSETDOUT
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.doutopts != self._config["channel_infos"][chid].doutopts:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_smpfilter(
        self, chid: int, attr_value: int, timeout: float = 0.0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.smpfilter = attr_value
        pkt.header.type = CBPacketType.CHANSETSMP
        event = self._config_events["chaninfo"] if timeout > 0 else None

        if not self._send_packet(pkt=pkt, event=event, timeout=timeout):
            self.get_config(timeout=GET_CONFIG_TIMEOUT, force_refresh=True)

            if pkt.smpfilter != self._config["channel_infos"][chid].smpfilter:
                raise RuntimeError(
                    "Packet response contents do not match expected values."
                )
            else:
                raise RuntimeError(
                    "Valid packet response NOT received, but packet contains expected values"
                )

    def _configure_channel_enable_spike(
        self, chid: int, attr_value: bool, timeout: float = 0
    ):
        pkt = copy.copy(self._config["channel_infos"][chid])
        pkt.header.type = CBPacketType.CHANSETSPK
        pkt.spkopts &= ~CBAInpSpk.EXTRACT.value
        if attr_value:
            pkt.spkopts |= CBAInpSpk.EXTRACT.value if attr_value else 0
            # Also reset sorting. Enable hoops by default.
            pkt.spkopts &= ~CBAInpSpk.ALLSORT.value
            pkt.spkopts |= CBAInpSpk.HOOPSORT.value

        timeout = 0.1
        event = self._config_events["chaninfo"] if timeout > 0 else None
        self._send_packet(pkt=pkt, event=event, timeout=timeout)

    def configure_channel(
        self, chid: int, attr_name: str, attr_value, timeout: float = 0
    ):
        """
        attr_name: try label, smpgroup, autothreshold, lnc
        attr_value: overwrite with this value
        timout: if set to non-zero value, network exchange become blocking,
            and function call blocks until response is received or timeout
            is reached
            warning: can dramatically slow down network performance
        """
        # this won't raise an exception if the name is not valid
        if attr_name.lower() in self._config_func_map:
            # self._config_events["chaninfo"].clear()
            # time.sleep(0.005)  # Sometimes setting the event is slower than the response?!
            self._config_func_map[attr_name.lower()](chid, attr_value, timeout)
            # self._config_events["chaninfo"].wait(timeout=0.02)
        else:
            # so let the user know, TODO: raise an exception?
            print(f"{attr_name} is not a recognized name.")

    def configure_all_channels(
        self, chtype: CBChannelType, attr_name: str, attr_value, timeout: float
    ):
        for chid, ch_info in self._config["channel_infos"].items():
            if self._config["channel_types"][chid] == chtype:
                self.configure_channel(chid, attr_name, attr_value, timeout)

    def configure_channel_spike(
        self, chid: int, attr_name: str, attr_value: any, timeout: float = 0
    ):
        # self._config_events["chaninfo"].clear()
        # time.sleep(0.005)  # Sometimes setting the event is slower than the response?!
        if attr_name.lower().startswith("enable"):
            self._configure_channel_enable_spike(chid, attr_value, timeout)
        elif attr_name.lower().startswith("autothresh"):
            self._configure_channel_autothreshold(chid, attr_value, timeout)
        elif attr_name.lower().startswith("hoops"):
            self._configure_channel_hoops(chid, attr_value, timeout)
        # self._config_events["chaninfo"].wait(timeout=0.02)

    def configure_all_channels_spike(
        self, chtype: CBChannelType, attr_name: str, attr_value, timeout: float
    ):
        for chid, ch_info in self._config["channel_infos"].items():
            if self._config["channel_types"][chid] == chtype:
                self.configure_channel_spike(chid, attr_name, attr_value, timeout)

    def configure_channel_disable(self, chid: int):
        ch_pkt = copy.copy(self._config["channel_infos"][chid])
        ch_pkt.spkopts &= ~CBAInpSpk.EXTRACT.value  # Disable spiking
        ch_pkt.spkopts &= ~CBAInpSpk.THRAUTO.value  # Disable auto-thresholding
        ch_pkt.ainpopts &= ~CBAnaInpOpts.refelec_offsetcorrect  # Disable DC offset
        ch_pkt.ainpopts &= ~CBAnaInpOpts.lnc_mask  # Disable LNC
        ch_pkt.ainpopts &= ~CBAnaInpOpts.refelec_mask  # Disable refelec_mask
        ch_pkt.ainpopts |= ~CBAnaInpOpts.refelec_rawstream  # disable raw
        ch_pkt.smpgroup = 0
        ch_pkt.smpfilter = 0
        self.configure_channel_by_packet(ch_pkt)

    def configure_all_channels_disable(self, chtype: CBChannelType):
        for chid, _type in self._config["channel_types"].items():
            if _type == chtype:
                self.configure_channel_disable(chid)

    def configure_channel_by_packet(self, packet: Structure):
        # If the data were coming through serialized, we could create a fresh packet with...
        # packet = self.packet_factory.make_packet(bytes(packet))
        packet.header.type = CBPacketType.CHANSET
        self._send_packet(packet, event=self._config_events["chaninfo"])

    def get_config(
        self, timeout: Optional[float] = None, force_refresh: bool = True
    ) -> Optional[dict]:
        """
        See CereLink cbCFGBUFF and how/where this gets filled.
        """
        if force_refresh:
            # Clear out our existing config
            self._config["proc_chans"] = 0
            self._config["channel_infos"] = {}
            # Do not clear sysfreq if we already have it as this cannot change.
            self._config["sysfreq"] = self._config.get("sysfreq", None)
            # self._config["instrument"] = -1
            time.sleep(0.1)
            pkt = self.packet_factory.make_packet(
                None,
                chid=CBSpecialChan.CONFIGURATION,
                pkt_type=CBPacketType.REQCONFIGALL,
            )
            pkt.header.time = 1
            pkt.header.dlen = 0
            # REQCONFIGALL packet should trigger a cascade (see main.c recv_pkt):
            #  1. echo back the REQCONFIGALL packet
            #  2. PROCINFO --> .chancount can tell us how many channels to expect.
            #  3-4. SS_DETECT, SS_ARTIF_REJECT
            #  5. n_chans * SS_NOISE_BOUNDARY
            #  6-7. SS_STATISTICS, SS_STATUS
            #  8. 6 * GROUPINFO
            #  9. 12 * FILTINFO
            # 10. b (14) * BANKINFO
            # 11. n_chans * CHANINFO
            # 12. n_chans * NTRODEINFO
            # 13. n_chans * 2 * SS_MODELSET
            # 14. LNC
            # 15. FILECFG
            # 16. SYSINFO
            # We wait on the final SYSINFO packet. Unfortunately this is commonly dropped,
            #  especially if we are slow to handle the preceding packets.
            #  But we can still return success if we got all the chaninfo packets.
            if not self._send_packet(
                pkt, event=self._config_events["sysrep"], timeout=timeout
            ):
                logger.debug("Did not receive final response to REQCONFIGALL.")
            n_infos = len(self._config["channel_infos"])
            if self._config["proc_chans"] == 0 or n_infos != self._config["proc_chans"]:
                logger.warning(
                    f"Received incomplete response to REQCONFIGALL "
                    f"({n_infos} / {self._config['proc_chans']} CHANINFOS)."
                )
                return None
            else:
                logger.info(f"Received {self._config['proc_chans']} CHANINFO packets.")
        return self.config.copy()

    def set_nplay_state(
        self,
        val: int = 0,
        mode: CBNPlayMode = CBNPlayMode.NONE,
        flag: CBNPlayFlag = CBNPlayFlag.NONE,
        speed: float = 1,
    ):
        pkt = self.packet_factory.make_packet(bytes(self._config["nplay"]))
        # pkt = self.packet_factory.make_packet(None,
        #                                       chid=CBSpecialChan.CONFIGURATION,
        #                                       pkt_type=CBPacketType.NPLAYSET)
        pkt.header.type = CBPacketType.NPLAYSET
        pkt.mode = mode
        pkt.flags = flag
        pkt.val = val
        pkt.speed = speed
        # if 'nplay' in self._config and self._config['nplay'] is not None:
        #     pkt.fname = self._config['nplay'].fname
        self._send_packet(pkt)

    def set_runlevel(
        self, run_level: CBRunLevel, timeout: Optional[float] = None
    ) -> CBError:
        """
        cbPKT_SYSINFO sysinfo;
        sysinfo.type     = cbPKTTYPE_SYSSETRUNLEV;
        sysinfo.runlevel = runlevel;
        sysinfo.resetque = resetque;
        sysinfo.runflags = runflags;
        """
        pkt = self.packet_factory.make_packet(
            None, chid=CBSpecialChan.CONFIGURATION, pkt_type=CBPacketType.SYSSETRUNLEV
        )
        pkt.runlevel = run_level
        pkt.header.time = 1
        if run_level == CBRunLevel.HARDRESET:
            event = self._config_events["runlevel_standby"]
        elif run_level == CBRunLevel.RESET:
            event = self._config_events["runlevel_running"]
        else:
            event = self._config_events["sysrep"]
        logger.debug(f"Attempting to set runlevel to {run_level}")
        succ = self._send_packet(pkt, event=event, timeout=timeout)
        if not succ:
            logger.warning("Did not receive SYSREPRUNLEV in expected timeout.")
            return CBError.NOREPLY
        else:
            return CBError.NONE

    def get_runlevel(self, force_refresh=False) -> CBRunLevel:
        if force_refresh:
            err = self.set_runlevel(CBRunLevel.RUNNING, timeout=0.5)
        return self._config["runlevel"]

    def set_transport(
        self, transport: str, value: bool, timeout: Optional[float] = None
    ):
        pkt = self.packet_factory.make_packet(
            None,
            chid=CBSpecialChan.CONFIGURATION,
            pkt_type=CBPacketType.SYSSETTRANSPORT,
        )
        flag = {
            "CHECK": CBTransport.CHECK,
            "UDP": CBTransport.UDP,
            "LSL": CBTransport.LSL,
            "USB": CBTransport.USB,
            "SERIAL": CBTransport.SERIAL,
            "ALL": 0xFFFF,
        }[transport.upper()]
        if value:
            pkt.transport |= flag
        else:
            pkt.transport &= ~flag
        event = self._config_events["sysrep"]
        logger.debug(f"Attempting to set transport to {transport.upper()}")
        if not self._send_packet(pkt, event=event, timeout=timeout):
            logger.warning("Did not receive SYSREPTRANSPORT in expected timeout.")

    def get_transport(self, force_refresh=False) -> int:
        if force_refresh:
            self.set_transport("CHECK", True, timeout=0.5)
        return self._config["transport"]

    def get_monitor_state(self) -> dict:
        return self._monitor_state.copy()

    def send_comment(self, comment: str, timestamp: Optional[int] = None):
        pkt = self.packet_factory.make_packet(
            None, chid=CBSpecialChan.CONFIGURATION, pkt_type=CBPacketType.COMMENTSET
        )
        # Property setter should handle converting Python string to C string.
        pkt.comment = comment
        if hasattr(pkt, "timeStarted"):
            pkt.timeStarted = timestamp or self.last_time
        # pkt.comment = bytes(create_string_buffer(comment.encode("utf-8"), 256))
        logger.debug(f"Sending comment (timeStarted: {pkt.timeStarted}): {pkt.comment}")
        self._send_packet(pkt)
        return 0

    def reset(self) -> int:
        print("TODO: reset NSP proctime to 0")
        return 0

    # endregion

    # region IO
    def connect(self, startup_sequence: bool = True) -> int:
        self._io_thread = CerebusDatagramThread(
            self._pkt_handler_thread.receiver_queue,
            self._local_addr,
            self._device_addr,
            self._params.protocol,
            self._params.recv_bufsize,
        )
        self._io_thread.start()
        # _io_thread.start() returns immediately but takes a few moments until its send_q is created.
        time.sleep(0.5)

        err = CBError.NONE
        runlevel = 0

        # Startup sequence runs in a short-lived async chain.
        #  It relies on both the sender and receiver working.
        if startup_sequence:
            err = self._startup_sequence()

        if not err:
            runlevel = self.get_runlevel(force_refresh=not startup_sequence)
            if not runlevel:
                err = CBError.UNDEFINED

        if err:
            if err == CBError.NOREPLY:
                logger.error(
                    "Device did not reply to startup sequence. This could be caused by a network problem "
                    "or by a protocol mismatch."
                )
            else:
                logger.error(f"Error received during startup sequence: {err}")
            self.disconnect()

        return runlevel

    def disconnect(self):
        # TODO: Terminate IO
        self._io_thread.stop()
        self._pkt_handler_thread.stop()

        self._io_thread.join()
        self._pkt_handler_thread.join()

        logger.info("Disconnected successfully.")

    def _startup_sequence(self) -> CBError:
        err = self.set_runlevel(CBRunLevel.RUNNING, timeout=0.45)
        if err != CBError.NONE:
            return err

        if self._config["runlevel"] != CBRunLevel.RUNNING:
            # After a cold boot, the system is probably in runlevel 10 (startup)
            # Central does not attempt to reset until 500 msec after the initial runlevel check.
            # We will receive 2 runlevel packets. 20 to acknowledge the hard reset, the 30 when it's in standby.
            err = self.set_runlevel(
                CBRunLevel.HARDRESET, timeout=0.45
            )  # Doesn't return until standby is received.

        # Central waits another 0.5 seconds before requesting the config, even if already running.
        # We don't do that here.

        logger.debug("Attempting to get_config")
        _cfg = self.get_config(timeout=GET_CONFIG_TIMEOUT)

        if self._config["runlevel"] != CBRunLevel.RUNNING:
            # Central waits a full second between the reqconfigall and reset
            # We will receive 2 runlevel packets. 40 to acknowledge the reset, and 50 when it's running.
            err = self.set_runlevel(CBRunLevel.RESET)
            # Note: no timeout! Will block until RUNNING is received.

            # time.sleep(0.1)  # Give it enough time to finish starting up.

        if self._config["nplay"] is not None:
            # 1. (skip) mode=CBNPlayMode.PATH, fname=folder_path.
            # 2. mode=CBNPlayMode.NONE, speed=1, fname=filename. These are the default settings.
            self.set_nplay_state()
            time.sleep(0.2)
            # 3. Unpause: mode=CBNPlayMode.PAUSE, val=0, speed=1
            self.set_nplay_state(val=0, mode=CBNPlayMode.PAUSE)
            time.sleep(0.1)
            # 4. mode=CBNPlayMode.SINGLE, val=0, speed=0??
            self.set_nplay_state(val=0, mode=CBNPlayMode.SINGLE, speed=0)
            time.sleep(0.1)
            # set unpause

        return CBError.NONE

    def _send_packet(
        self, pkt, event: Optional[threading.Event] = None, timeout=0.005
    ) -> bool:
        """
        Touch-up packet and enqueue for sender thread.
        Called by configure and _startup_sequence.
        """
        pkt.header.time = pkt.header.time or self.last_time
        send_bytes = bytes(pkt)
        # The firmware truncates its struct sizes to a multiple of 4-bytes and will complain if we send
        #  something too big.
        n_bytes = len(send_bytes)
        n_send = n_bytes - n_bytes % 4
        if n_send != n_bytes:
            logger.debug("Truncating packet with nbytes not a multiple of 4.")
        send_bytes = send_bytes[:n_send]
        if event is not None:
            event.clear()
        self._io_thread.send(send_bytes)
        if event is not None:
            res = event.wait(timeout=timeout)
            if not res:
                logger.debug("timeout expired waiting for event")
                return False
        return True

    # endregion
