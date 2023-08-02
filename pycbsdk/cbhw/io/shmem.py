import sys
import threading
import queue
from functools import partial

from .base import CerebusCommInterface
from ..packet.factory import CBPacketFactory


f_open_mutex_partial = None
f_close_handle = None
f_open_event_partial = None
f_open_mapping_partial = None
f_map_view = None
f_wait_object = None
if sys.platform.lower() == "win32":
    from ctypes import windll, wintypes

    f_open_mutex = windll.kernel32.OpenMutexW
    f_open_mutex.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    f_open_mutex.restype = wintypes.HANDLE
    f_close_handle = windll.kernel32.CloseHandle

    f_open_event = windll.kernel32.OpenEventW
    f_open_event.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    f_open_event.restype = wintypes.HANDLE

    f_open_mapping = windll.kernel32.OpenFileMappingW
    f_open_mapping.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    f_open_mapping.restype = wintypes.HANDLE

    f_map_view = windll.kernel32.MapViewOfFile
    # f_map_view.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.SIZE]
    f_map_view.restype = wintypes.LPVOID

    f_wait_object = windll.kernel32.WaitForSingleObject
    f_wait_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    f_wait_object.restype = wintypes.DWORD

    STANDARD_RIGHTS_REQUIRED = 0xF0000
    SYNCHRONIZE = 0x100000
    MUTANT_QUERY_STATE = 0x1
    MUTEX_ALL_ACCESS = STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | MUTANT_QUERY_STATE
    f_open_mutex_partial = partial(f_open_mutex, MUTEX_ALL_ACCESS, 0)
    f_open_event_partial = partial(f_open_event, SYNCHRONIZE, 1)
    FILE_MAP_READ = 0x0004
    f_open_mapping_partial = partial(f_open_mapping, FILE_MAP_READ, 0)


def check_cerebus_shmem(cerebus_mutex: str = "cbSharedDataMutex"):
    h_mutex = 0
    if f_open_mutex_partial is not None:
        h_mutex = f_open_mutex_partial(cerebus_mutex)
        f_close_handle(h_mutex)
    return h_mutex


class CerebusShmemThread(threading.Thread, CerebusCommInterface):
    """
    Runs the receiver and sender async chains.
    """

    def __init__(
        self,
        receiver_queue: queue.SimpleQueue,
        protocol: str
    ):
        super().__init__()
        self._recv_q = receiver_queue
        self._packet_factory = CBPacketFactory(protocol=protocol)  # Just for the header
        self._h_sig = f_open_event_partial("cbSIGNALevent")
        self._n_processed = 0
        self._keep_running = False

        self._h_rec = f_open_mapping_partial("cbRECbuffer")
        self._rec_buff = f_map_view(self._h_rec, 0x0004, 0, 0, 0)
        # TODO: Cast self._rec_buff to cbRECBUFF

    def _wait_for_data(self) -> int:
        result = 11  # cbRESULT_NONEWDATA
        if f_wait_object is not None:
            if f_wait_object(self._h_sig, 250) == 0:
                result = 0  # cbRESULT_OK
            # elif not (cb_cfg_buffer_ptr[nIdx]->version):
            #     result = 2  # cbRESULT_NOCENTRALAPP
        return result

    def _check_for_data(self):
        # Calculate how many packets are remaining to be processed
        n_received = 0  # TODO: Get from self._rec_buff
        n_remaining = n_received - self._n_processed
        # Note: CereLink uses this function to check "Level of Concern" based on
        #  local tail and buffer head. If LOC is critical then it resets the local tail to the buffer head.
        #  Given that this thread isn't doing anything except pulling packets and enqueuing them,
        #  let's see how far we can get without having to reset our read indices.
        return n_remaining

    def _get_next_packet(self):
        res = {}
        # TODO: Get the next packet from self._rec_buff then update the read indices (and wraparound)
        return res

    def run(self):
        self._keep_running = True
        while self._keep_running:
            res = self._wait_for_data()
            if res == 0:
                n_packets = self._check_for_data()
                for pkt_idx in range(n_packets):
                    packet = self._get_next_packet()
                    pkt_tuple = (None,)  # TODO: Make a tuple out of the packet
                    self._recv_q.put(pkt_tuple)
                    self._n_processed += 1

    def stop(self):
        raise NotImplementedError

    def send(self, send_bytes):
        raise NotImplementedError
