from typing import Optional
from collections.abc import Callable
import sys
import logging

import ifaddr

from .cbhw.device.nsp import *
from .misc.net import ping
from .cbhw.params import Params
from .cbhw.packet.common import CBPacketType, CBChannelType


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
    "get_config",
    "reset_nsp",
    "register_spk_callback",
    "register_event_callback",
    "register_group_callback",
    "register_config_callback",
    "CBRunLevel",
]


def create_params(
    inst_addr: str = "",
    inst_port: int = 51002,
    client_addr: str = "",
    client_port: int = 51002,
    recv_bufsize: Optional[int] = None,
    protocol: str = "4.1",
) -> Params:
    params_obj = Params()
    if sys.platform == 'win32':
        if client_addr == "":
            for adapter in ifaddr.get_adapters():
                for ip in adapter.ips:
                    if ip.is_IPv4 and ip.ip.startswith("192.168.137"):
                        client_addr = ip.ip
                        break
                if client_addr != "":
                    logging.debug(f"Using adapter found with ip {client_addr}")
                    break
            if client_addr == "":
                raise ValueError("client_addr: Unable to find adapter with ip in expected Cerebus subnet. "
                                 "Please specify client_addr argument. If using nPlayServer on this machine, "
                                 "you may use '127.0.0.1'")
        if inst_addr == "":
            logging.warning("On Windows `inst_addr` must be set to the IP address of the device."
                            "We are attempting to find it for you...")
            if client_addr == "127.0.0.1":
                inst_addr = "127.0.0.1"
            else:
                # Search known device IP addresses.
                for _term in ["200", "201", "128"]:
                    _test_addr = "192.168.137." + _term
                    if ping(_test_addr):
                        inst_addr = _test_addr
                        break
                if inst_addr == "":
                    raise ValueError("inst_addr: Unable to find device at known addresses. "
                                     "Please specify inst_addr argument.")
                logging.warning(f"Using inst_addr={inst_addr}.")

    params_obj.inst_addr = inst_addr
    params_obj.inst_port = inst_port
    params_obj.client_addr = client_addr
    params_obj.client_port = client_port
    if recv_bufsize is not None:
        params_obj.recv_bufsize = recv_bufsize
    params_obj.protocol = protocol
    return params_obj


def get_device(params: Params) -> NSPDevice:
    return NSPDevice(params)


def connect(device: NSPDevice, startup_sequence: bool = True) -> int:
    return device.connect(startup_sequence=startup_sequence)


def disconnect(device: NSPDevice) -> int:
    return device.disconnect()


def set_config(device: NSPDevice, cfg_name: str, cfg_value) -> int:
    return device.configure(cfg_name, cfg_value)


def set_channel_config_by_packet(device: NSPDevice, packet: object) -> int:
    return device.configure_channel_by_packet(packet)


def set_channel_config(device: NSPDevice, chid: int, attr: str, value) -> int:
    return device.configure_channel(chid, attr, value)


def set_channel_spk_config(device: NSPDevice, chid: int, attr: str, value) -> int:
    return device.configure_channel_spike(chid, attr, value)


def get_config(device: NSPDevice, force_refresh: bool = True) -> dict:
    return device.get_config(timeout=5.0, force_refresh=force_refresh)


def get_type(device: NSPDevice):  # -> tuple[CBConnectionType, CBDeviceType]:
    return device.get_type()


def reset_nsp(device: NSPDevice) -> int:
    return device.set_runlevel(CBRunLevel.HARDRESET)


def set_transport(device: NSPDevice, transport: str, value: bool) -> int:
    return device.set_transport(transport, value)


def set_runlevel(device: NSPDevice, runlevel: CBRunLevel) -> int:
    return device.set_runlevel(runlevel)


def get_runlevel(device: NSPDevice) -> CBRunLevel:
    return device.get_runlevel()


def register_spk_callback(device: NSPDevice, func: Callable[[], None]) -> int:
    return register_event_callback(device, CBChannelType.FrontEnd, func)


def register_event_callback(
    device: NSPDevice, channel_type: CBChannelType, func: Callable[[], None]
) -> int:
    return device.register_event_callback(channel_type, func)


def register_group_callback(
    device: NSPDevice, group: int, func: Callable[[], None]
) -> int:
    # group: 1-6 for sampling group.
    return device.register_group_callback(group, func)


def unregister_group_callback(
    device: NSPDevice, group: int, func: Callable[[], None]
) -> int:
    # group: 1-6 for sampling group.
    return device.unregister_group_callback(group, func)


def register_config_callback(
    device: NSPDevice, packet_type: CBPacketType, func: Callable[[], None]
) -> int:
    return device.register_config_callback(packet_type, func)
