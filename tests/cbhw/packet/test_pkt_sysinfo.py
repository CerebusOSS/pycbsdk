from ctypes import sizeof
from pycbsdk.cbhw import config

config.protocol = "4.1"
from pycbsdk.cbhw.packet import packets


def test_pkt_sysinfo_structure():
    """
    Verify that there are no unexpected offsets in the packet structure.
    """
    cumu_bytes = 0
    for f, t in packets.CBPacketSysInfo._fields_:
        a = getattr(packets.CBPacketSysInfo, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_sysinfo_init_nodata():
    """
    Verify that the packet can be initialized without data.
    """
    pkt = packets.CBPacketSysInfo()
    assert pkt.header.chid == packets.CBSpecialChan.CONFIGURATION
    assert pkt.header.type == packets.CBPacketType.SYSSET
    assert (
        pkt.header.dlen
        == (sizeof(packets.CBPacketSysInfo) - sizeof(packets.CBPacketHeader)) // 4
    )


def test_pkt_sysinfo_init_data():
    """
    Verify that the packet can be initialized with data.
    """
    pkt = packets.CBPacketSysInfo()
    pkt.sysfreq = 30000
    pkt2 = packets.CBPacketSysInfo(bytes(pkt))
    assert pkt2.sysfreq == 30000


def test_pkt_sysinfo_modify():
    pkt = packets.CBPacketSysInfo()
    pkt.sysfreq = 30000
    pkt.spikelen = 60
    pkt.spikepre = 22
    assert pkt.sysfreq == 30000
    assert pkt.spikelen == 60
    assert pkt.spikepre == 22
