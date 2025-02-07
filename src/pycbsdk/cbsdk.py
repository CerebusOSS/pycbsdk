from ctypes import Structure
from typing import Optional
from collections.abc import Callable

from .cbhw.device.nsp import *
from .cbhw.params import Params
from .cbhw.packet.common import CBPacketType, CBChannelType, DEFAULT_TIMEOUT


"""
This module is intended to resemble a simple C interface.
We don't expose any classes. Only a couple objects are passed
back and forth but for the caller these are entirely opaque.

Any helper modules intended to improve usibility of pycbsdk
can only access the device and data through this module.
"""


# define __all__ so `from cbsdk import *` doesn't transitively import all of the cbhw classes.
__all__ = [
    "create_params",
    "get_device",
    "connect",
    "disconnect",
    "set_config",
    "set_channel_config_by_packet",
    "set_channel_disable",
    "set_all_channels_disable",
    "set_channel_config",
    "set_all_channels_config",
    "set_channel_spk_config",
    "set_all_channels_spk_config",
    "set_channel_continuous_raw_data",
    "get_config",
    "reset_nsp",
    "set_transport",
    "set_runlevel",
    "get_runlevel",
    "register_event_callback",
    "unregister_event_callback",
    "register_spk_callback",
    "unregister_spk_callback",
    "register_group_callback",
    "unregister_group_callback",
    "register_config_callback",
    "unregister_config_callback",
    "CBRunLevel",
]


# NOTE: When adding new functions, please make sure to add them to __all__ as well.


def create_params(
    inst_addr: str = "",
    inst_port: int = 51002,
    client_addr: str = "",
    client_port: int = 51002,
    recv_bufsize: Optional[int] = None,
    protocol: str = "4.1",
) -> Params:
    params_obj = Params(
        inst_addr=inst_addr,
        inst_port=inst_port,
        client_addr=client_addr,
        client_port=client_port,
        recv_bufsize=recv_bufsize,
        protocol=protocol,
    )

    return params_obj


def get_device(params: Params) -> NSPDevice:
    return NSPDevice(params)


def connect(device: NSPDevice, startup_sequence: bool = True) -> int:
    return device.connect(startup_sequence=startup_sequence)


def disconnect(device: NSPDevice):
    device.disconnect()


def set_config(device: NSPDevice, cfg_name: str, cfg_value):
    device.configure(cfg_name, cfg_value)


def set_channel_config_by_packet(device: NSPDevice, packet: Structure):
    device.configure_channel_by_packet(packet)


def set_channel_disable(device: NSPDevice, chid: int):
    device.configure_channel_disable(chid)


def set_all_channels_disable(device: NSPDevice, chtype: CBChannelType):
    device.configure_all_channels_disable(chtype)


def set_channel_config(
    device: NSPDevice, chid: int, attr: str, value, timeout: float = DEFAULT_TIMEOUT
):
    device.configure_channel(chid, attr, value, timeout=timeout)


def set_all_channels_config(
    device: NSPDevice,
    chtype: CBChannelType,
    attr: str,
    value,
    timeout: float = DEFAULT_TIMEOUT,
):
    device.configure_all_channels(chtype, attr, value, timeout)


def set_channel_spk_config(
    device: NSPDevice, chid: int, attr: str, value, timeout: float = DEFAULT_TIMEOUT
):
    device.configure_channel_spike(chid, attr, value, timeout)


def set_all_channels_spk_config(
    device: NSPDevice,
    chtype: CBChannelType,
    attr: str,
    value,
    timeout: float = DEFAULT_TIMEOUT,
):
    device.configure_all_channels_spike(chtype, attr, value, timeout)


def set_channel_continuous_raw_data(
    device: NSPDevice,
    chid: int,
    smpgroup: int,
    smpfilter: int,
    timeout: float = DEFAULT_TIMEOUT,
):
    set_channel_config(device, chid, attr="smpgroup", value=smpgroup, timeout=timeout)
    set_channel_config(device, chid, attr="smpfilter", value=smpfilter, timeout=timeout)
    set_channel_spk_config(device, chid, attr="enable", value=False, timeout=timeout)


def get_config(device: NSPDevice, force_refresh: bool = True) -> dict:
    return device.get_config(timeout=5.0, force_refresh=force_refresh)


# def get_type(device: NSPDevice):  # -> tuple[CBConnectionType, CBDeviceType]:
#     return device.get_type()


def reset_nsp(device: NSPDevice) -> int:
    # returns CBError.NONE (0) if successful.
    return device.set_runlevel(CBRunLevel.HARDRESET)


def set_transport(device: NSPDevice, transport: str, value: bool):
    device.set_transport(transport, value)


def set_runlevel(device: NSPDevice, runlevel: CBRunLevel) -> int:
    # returns CBError.NONE (0) if successful.
    return device.set_runlevel(runlevel)


def get_runlevel(device: NSPDevice) -> CBRunLevel:
    return device.get_runlevel()


def get_monitor_state(device: NSPDevice) -> dict:
    return device.get_monitor_state()


def set_comment(
    device: NSPDevice, comment: str, timestamp: Optional[int] = None
) -> int:
    return device.send_comment(comment, timestamp)


def register_event_callback(
    device: NSPDevice, channel_type: CBChannelType, func: Callable[[Structure], None]
):
    device.register_event_callback(channel_type, func)


def unregister_event_callback(
    device: NSPDevice, channel_type: CBChannelType, func: Callable[[Structure], None]
) -> int:
    return device.unregister_event_callback(channel_type, func)


def register_spk_callback(device: NSPDevice, func: Callable[[Structure], None]):
    register_event_callback(device, CBChannelType.FrontEnd, func)


def unregister_spk_callback(
    device: NSPDevice, func: Callable[[Structure], None]
) -> int:
    return unregister_event_callback(device, CBChannelType.FrontEnd, func)


def register_group_callback(
    device: NSPDevice, group: int, func: Callable[[Structure], None]
):
    # group: 1-6 for sampling group.
    device.register_group_callback(group, func)


def unregister_group_callback(
    device: NSPDevice, group: int, func: Callable[[Structure], None]
) -> int:
    # group: 1-6 for sampling group.
    return device.unregister_group_callback(group, func)


def register_config_callback(
    device: NSPDevice, packet_type: CBPacketType, func: Callable[[Structure], None]
):
    device.register_config_callback(packet_type, func)


def unregister_config_callback(
    device: NSPDevice, packet_type: CBPacketType, func: Callable[[Structure], None]
) -> int:
    return device.unregister_config_callback(packet_type, func)


def register_comment_callback(device: NSPDevice, func: Callable[[Structure], None]):
    register_config_callback(device, CBPacketType.COMMENTREP, func)


def unregister_comment_callback(
    device: NSPDevice, func: Callable[[Structure], None]
) -> int:
    return unregister_config_callback(device, CBPacketType.COMMENTREP, func)
