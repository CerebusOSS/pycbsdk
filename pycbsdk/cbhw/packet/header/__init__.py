from ... import config


if config.protocol is None:
    raise ValueError(
        "config.protocol must be set before importing from pycbsdk.cbhw.packet"
    )


if int(config.protocol[0]) <= 3:
    from .v311 import CBPacketHeader
elif int(config.protocol[0]) == 4 and int(config.protocol.split(".")[1]) < 1:
    from .v40 import CBPacketHeader
else:
    from .v41 import CBPacketHeader
