from collections import defaultdict
import threading

from pycbsdk.cbhw.packet.common import CBChannelType
from pycbsdk.cbhw.packet.factory import CBPacketFactory
from pycbsdk.cbhw.params import Params


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
            "channel_infos": {},
            "group_infos": {},
        }
        self.config_callbacks = defaultdict(
            lambda: []
        )  # Keyed by pkt.header.type: CBPacketType
        self.group_callbacks = {_: [] for _ in range(1, 7)}  # 1-5:SMP; 6:RAW
        self.event_callbacks = defaultdict(
            lambda: []
        )  # Keyed by self._config['channel_types'][chid]
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
