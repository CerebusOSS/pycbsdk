import sys
import argparse
import logging

from pycbsdk import cbsdk
from pycbsdk.cbhw.packet.common import CBChannelType
import time
import numpy as np


logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger(__name__)


class DummyApp:
    def __init__(self, duration=21.0):
        n_samples = int(np.ceil(duration * 30_000))
        self._buffer = np.zeros((n_samples, 2), dtype=np.int16)
        self._ts = np.zeros((n_samples,), dtype=np.int64)
        self._write_index = 0
        self._last_time = 0

    def handle_frame(self, pkt):
        if self._write_index < self._buffer.shape[0]:
            self._buffer[self._write_index, :] = memoryview(pkt.data[:4])
            self._ts[self._write_index] = pkt.header.time
            self._write_index += 1

    def finish(self):
        b_ts = self._ts > 0
        if np.any(b_ts):
            print(
                f"Collected {np.sum(b_ts)} samples in {(self._ts[b_ts][-1] - self._ts[b_ts][0]) / 1e9} s"
            )
            print(np.mean(np.diff(self._ts[b_ts])))


def run(duration=11.0, **params_kwargs):
    """
    Run the application:
    - Configure the connection to the nsp
    - Register a callback that handles the spikes and updates internal state
    - Run the async chain
    - On the main thread, render the internal state (print the min-max mean+/-std of the rates every 0.5 seconds).
    """
    params_obj = cbsdk.create_params(**params_kwargs)
    nsp_obj = cbsdk.get_device(params_obj)
    _ = cbsdk.connect(nsp_obj, startup_sequence=True)
    config = cbsdk.get_config(nsp_obj)

    # Disable all channels.
    for chid in [
        k
        for k, v in config["channel_types"].items()
        if v in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]
    ]:
        _ = cbsdk.set_channel_spk_config(nsp_obj, chid, "enable", False)
        _ = cbsdk.set_channel_config(nsp_obj, chid, "smpgroup", 0)

    # Enable channel 1 raw.
    _ = cbsdk.set_channel_config(nsp_obj, 1, "smpgroup", 6)

    # Create a dummy app.
    app = DummyApp(duration=duration)

    time.sleep(2.0)

    # Register callbacks to update the app's state when appropriate packets are received.
    _ = cbsdk.register_group_callback(nsp_obj, 6, app.handle_frame)

    t_start = time.time()
    try:
        t_elapsed = time.time() - t_start
        while t_elapsed < duration:
            time.sleep(1.0)
            t_elapsed = time.time() - t_start
    except KeyboardInterrupt:
        pass
    finally:
        app.finish()
        _ = cbsdk.disconnect(nsp_obj)


def main():
    # --inst_addr=192.168.137.255 --client_addr=192.168.137.199
    parser = argparse.ArgumentParser(description="Consume data from (emulated) NSP.")
    parser.add_argument(
        "--inst_addr",
        "-i",
        type=str,
        default="",
        help="ipv4 address to send control packets. Can use subnet. "
        "Will broadcast if not on Cerebus Subnet."
        "Use 127.0.0.1 if using with nPlayServer in non-bcast.",
    )
    parser.add_argument("--inst_port", type=int, default=51002)
    parser.add_argument(
        "--client_addr",
        "-c",
        type=str,
        default="",
        help="ipv4 address of the adapter we will receive packets on. "
        "Defaults to INADDR_ANY. If address is provided, assumes Cerebus Subnet.",
    )
    parser.add_argument("--client_port", "-p", type=int, default=51002)
    parser.add_argument(
        "--recv_bufsize",
        "-b",
        type=int,
        help=f"UDP socket recv buffer size. "
        f"Default: {(8 if sys.platform == 'win32' else 6) * 1024 * 1024}.",
    )
    parser.add_argument("--protocol", type=str, default="4.1")
    parser.add_argument(
        "--duration",
        type=float,
        default=11.0,
        help="Intervals will be calculated on data collected over this duration.",
    )
    parser.add_argument(
        "--debug",
        "-d",
        help="Print lots of debugging statements",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        help="Be verbose",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
    )
    args = parser.parse_args()
    kwargs = vars(args)

    logger.setLevel(kwargs.pop("loglevel"))
    run(**kwargs)


if __name__ == "__main__":
    main()
