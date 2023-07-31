import pytest
from pycbsdk.cbhw import packet
from ctypes import sizeof


def test_pkt_header_structure():
    """
    Verify that there are no unexpected offsets in the structure.
    """
    cumu_bytes = 0
    for f, t in packet.CBPacketHeader._fields_:
        a = getattr(packet.CBPacketHeader, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_header_init_noargs():
    """
    Test the CBPacketHeader class init function with no args.
    """
    pkt_header = packet.CBPacketHeader()
    assert pkt_header.time == 0
    assert pkt_header.chid == 0
    assert pkt_header.type == 0
    assert pkt_header.dlen == 0
    assert sizeof(pkt_header) == packet.HEADER_SIZE


def test_pkt_header_from_buffer():
    """
    Test the CBPacketHeader class creation from a buffer.
    """
    pkt_header = packet.CBPacketHeader.from_buffer_copy(
        b"\x01\x00\x00\x00\x02\x00\x03\x04"
    )
    assert pkt_header.time == 1
    assert pkt_header.chid == 2
    assert pkt_header.type == 3
    assert pkt_header.dlen == 4
