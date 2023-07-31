import struct

import numpy as np
from ctypes import sizeof

from pycbsdk.cbhw import packet


def test_pkt_spike_structure():
    """
    Verify that there are no unexpected offsets in the packet structure.
    """
    cumu_bytes = 0
    for f, t in packet.CBPacketSpike._fields_:
        a = getattr(packet.CBPacketSpike, f)
        assert a.offset == cumu_bytes
        cumu_bytes += a.size


def test_pkt_spike_init_no_data():
    pkt = packet.CBPacketSpike()
    assert pkt.header.chid > 0  # Could assert that it's a valid spike-enabled channel.
    assert pkt.wave.dtype == "int16"
    assert pkt.wave.size == 0


def test_pkt_spike_init_data_nowave():
    header_bytes = bytes(
        packet.CBPacketSpike().header
    )  # Just to get the correct default values for no-wave pkt.
    fPattern = struct.pack("<3f", 1.0, 2.0, 3.0)
    nPeak = struct.pack("<H", 1)
    nValley = struct.pack("<H", 2)
    pkt = packet.CBPacketSpike(header_bytes + fPattern + nPeak + nValley)
    assert (
        pkt.header.dlen
        == (sizeof(packet.CBPacketSpike) - sizeof(packet.CBPacketHeader)) // 4
    )
    assert pkt.wave.size == 0
    assert pkt.nPeak == 1
    assert pkt.nValley == 2
    assert len(pkt.fPattern) == 3
    assert type(pkt.fPattern[0]) == float


def test_pkt_spike_init_data_withwave():

    fPattern = struct.pack("<3f", 1.0, 2.0, 3.0)
    nPeak = struct.pack("<H", 1)
    nValley = struct.pack("<H", 2)
    NPTS = 10  # TODO: Test odd number. Last entry probably gets cut off!? Need ceil instead of //.
    wave = struct.pack(f"<{NPTS}h", *range(NPTS))
    _header = packet.CBPacketSpike().header
    _header.dlen += (
        NPTS * sizeof(packet.CBPacketSpike._array._type_)
    ) // 4  # To accommodate waveform
    header_bytes = bytes(_header)

    # Try .from_buffer_copy. This will fail to fill variable length array.
    pkt1 = packet.CBPacketSpike.from_buffer_copy(
        header_bytes + fPattern + nPeak + nValley + wave
    )
    assert pkt1.wave.size == 0

    # Try as constructor argument. This will fill variable length array.
    pkt2 = packet.CBPacketSpike(header_bytes + fPattern + nPeak + nValley + wave)
    assert pkt2.wave.size == NPTS
    assert pkt2.wave.dtype == "int16"
    assert np.array_equal(pkt2.wave, np.arange(NPTS, dtype="int16"))

    # From another pkt
    pkt3 = packet.CBPacketSpike(bytes(pkt2))
    assert np.array_equal(pkt3.wave, np.arange(NPTS, dtype="int16"))


def test_pkt_spike_modify_wave():
    NPTS = 12
    bpp = sizeof(packet.CBPacketSpike._array._type_)  # bytes per point
    # Build a fresh spike packet
    pkt = packet.CBPacketSpike()
    pkt.header.chid = 14
    pkt.unit = 2

    # Create a packet and set waveform with a list
    import copy

    pkt1 = copy.copy(pkt)
    pkt1.wave = list(range(NPTS))

    # Create a packet and set waveform with a numpy array
    pkt2 = copy.copy(pkt)
    pkt2.wave = np.arange(NPTS, dtype="int16")

    for test_pkt in [pkt1, pkt2]:
        assert test_pkt.unit == 2
        assert test_pkt.wave.size == NPTS
        assert test_pkt.wave.dtype == "int16"
        assert np.array_equal(test_pkt.wave, np.arange(NPTS, dtype="int16"))
        assert (
            test_pkt.header.dlen
            == (
                sizeof(packet.CBPacketSpike)
                - sizeof(packet.CBPacketHeader)
                + NPTS * bpp
            )
            // 4
        )
