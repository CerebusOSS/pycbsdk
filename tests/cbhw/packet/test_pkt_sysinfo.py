from ctypes import sizeof
from pycbsdk.cbhw import packet


def test_pkt_sysinfo_structure():
    """
    Verify that there are no unexpected offsets in the packet structure.
    """
    cumu_bytes = 0
    for f, t in packet.CBPacketSysInfo._fields_:
        a = getattr(packet.CBPacketSysInfo, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_sysinfo_init_nodata():
    """
    Verify that the packet can be initialized without data.
    """
    pkt = packet.CBPacketSysInfo()
    assert pkt.header.chid == packet.CBPacketChan.CONFIGURATION
    assert pkt.header.type == packet.CBPacketType.SYSSET
    assert (
        pkt.header.dlen
        == (sizeof(packet.CBPacketSysInfo) - sizeof(packet.CBPacketHeader)) // 4
    )


def test_pkt_sysinfo_init_data():
    """
    Verify that the packet can be initialized with data.
    """
    pkt = packet.CBPacketSysInfo()
    pkt.sysfreq = 30000
    pkt2 = packet.CBPacketSysInfo(bytes(pkt))
    assert pkt2.sysfreq == 30000


def test_pkt_sysinfo_modify():
    pkt = packet.CBPacketSysInfo()
    pkt.sysfreq = 30000
    pkt.spikelen = 60
    pkt.spikepre = 22
    assert pkt.sysfreq == 30000
    assert pkt.spikelen == 60
    assert pkt.spikepre == 22
