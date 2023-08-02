from typing import Optional
import logging
import sys

import ifaddr

from ..misc.net import ping


class Params:
    """
    Emulate an opaque C structure storing API parameters.
    For future extensibility, the API does not expose this structure directly and it can only be modified
    through setters and getters.
    (Note: it would be more future-proof if we used e.g., set_param(opaque_params, "param_name", new_value),
     but I'm not a complete masochist so I'll leverage Python's property functionality for this prototype.)
    """

    def __init__(self,
                 inst_addr: str = "",
                 inst_port: int = 51002,
                 client_addr: str = "",
                 client_port: int = 51002,
                 recv_bufsize: Optional[int] = None,
                 protocol: str = "4.1"):
        if client_addr == "":
            # We need to specify the machine's network adapter IP address, depending on the platform.
            if sys.platform.lower() == "win32":
                # In Windows, we cannot use a netmask. We must specify the IP exactly. So we search for it.
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
            elif sys.platform.lower() == "linux":
                # On Linux, IPADDR_ANY sort of works, but many packets are lost. We can however use a netmask.
                client_addr = "192.168.137.255"
            else:
                # On Macs, we can use a netmask of 255.255.255.255, or leave it blank which defaults to 0.0.0.0
                #  which is a synonym for IPADDR_ANY. This seems to work well.
                pass
        if inst_addr == "":
            # We need to specify the instrument IP address, depending on the platform.
            if client_addr == "127.0.0.1":
                logging.info("Since local adapter is localhost, we will assume instrument is localhost too.")
                inst_addr = "127.0.0.1"
            else:
                logging.warning("`inst_addr` must be set to the IP address of the device."
                                "We are attempting to find it for you using known device ips...")
                for _term in ["200", "201", "128"]:
                    _test_addr = "192.168.137." + _term
                    if ping(_test_addr):
                        inst_addr = _test_addr
                        break
                if inst_addr == "":
                    raise ValueError("inst_addr: Unable to find device at known addresses. "
                                     "Please specify inst_addr argument.")
                logging.warning(f"Using inst_addr={inst_addr}.")

        self._inst_addr = inst_addr
        self._inst_port = inst_port
        self._client_addr = client_addr
        self._client_port = client_port
        self._recv_bufsize = recv_bufsize if recv_bufsize is not None else (8 if sys.platform == "win32" else 6) * 1024 * 1024
        self._protocol = protocol

    def __str__(self):
        return f"From Adapter {self._client_addr}:{self._client_port}\n" \
               f"To Device {self._inst_addr}:{self._inst_port}\n" \
               f"Using Protocol {self._protocol} and socket buffer size {self._recv_bufsize}"

    @property
    def inst_addr(self) -> str:
        return self._inst_addr

    @inst_addr.setter
    def inst_addr(self, value: str):
        self._inst_addr = value

    @property
    def inst_port(self) -> int:
        return self._inst_port

    @inst_port.setter
    def inst_port(self, value: int):
        self._inst_port = value

    @property
    def client_addr(self) -> str:
        return self._client_addr

    @client_addr.setter
    def client_addr(self, value: str):
        self._client_addr = value

    @property
    def client_port(self) -> int:
        return self._client_port

    @client_port.setter
    def client_port(self, value: int):
        self._client_port = value

    @property
    def recv_bufsize(self) -> int:
        return self._recv_bufsize

    @recv_bufsize.setter
    def recv_bufsize(self, value: int):
        self._recv_bufsize = value

    @property
    def protocol(self) -> str:
        return self._protocol

    @protocol.setter
    def protocol(self, value: str):
        self._protocol = value
