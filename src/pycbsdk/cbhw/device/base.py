from collections import defaultdict
from ctypes import Structure
import threading
import typing

from pycbsdk.cbhw.packet.common import CBChannelType, CBPacketType
from pycbsdk.cbhw.packet.factory import CBPacketFactory
from pycbsdk.cbhw.params import Params


CBPktCallBack = typing.Callable[[Structure], None]


class DeviceInterface:
    """
    Abstract class to define interface needed by NSPDataProtocol.
    Implementation is below in NSPConnection.
    """

    def __init__(self, params: Params):
        self._config_events = {
            "sysrep": threading.Event(),
            "runlevel_standby": threading.Event(),
            "runlevel_running": threading.Event(),
            "chaninfo": threading.Event(),
        }
        self._config = {
            "channel_types": defaultdict(
                lambda: CBChannelType.Any
            ),  # Filled in upon receiving device config.
            "proc_chans": 0,
            "instrument": -1,
            "channel_infos": {},
            "group_infos": {},
            "group_nchans": {},
            "sysfreq": None,  # Should be 30_000 for legacy or 1e9 for Gemini PTP
        }
        # Init group_callbacks dict with an empty list for each supported smp grp (1-5:SMP; 6:RAW)
        self.group_callbacks: typing.Dict[int, typing.List[CBPktCallBack]] = {
            _: [] for _ in range(1, 7)
        }
        # Init event_callbacks with an empty list for each known channel type.
        self.event_callbacks: typing.Dict[CBChannelType, typing.List[CBPktCallBack]] = {
            _: [] for _ in CBChannelType
        }
        # Init config_callbacks as a defaultdict that will create an empty list on-the-fly for unseen keys.
        self.config_callbacks: defaultdict[CBPacketType, typing.List[CBPktCallBack]] = (
            defaultdict(lambda: [])
        )
        self._params = params
        self.packet_factory = CBPacketFactory(protocol=self._params.protocol)
        self.pkts_received = 0
        self._monitor_state = {"counter": 0, "time": 0, "pkts_received": 0}

    @property
    def device_addr(self) -> tuple[str, int]:
        raise NotImplementedError

    @property
    def config(self) -> dict:
        return self._config
