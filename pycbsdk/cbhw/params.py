import logging
import sys


class Params:
    """
    Emulate an opaque C structure storing API parameters.
    For future extensibility, the API does not expose this structure directly and it can only be modified
    through setters and getters.
    (Note: it would be more future-proof if we used e.g., set_param(opaque_params, "param_name", new_value),
     but I'm not a complete masochist so I'll leverage Python's property functionality for this prototype.)
    """

    def __init__(self):
        self._inst_addr = ""
        self._inst_port = 51001
        self._client_addr = ""
        self._client_port = 51002
        self._recv_bufsize = (8 if sys.platform == "win32" else 6) * 1024 * 1024
        self._protocol = "4.1"

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
