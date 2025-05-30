import sys
import logging

from pycbsdk import cbsdk
from pycbsdk.cbhw.packet.common import CBChannelType
import time
import numpy as np


logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger(__name__)


class DummyApp:
    def __init__(self, nchans: int, duration=21.0, t_step=1 / 30_000):
        n_samples = int(np.ceil(duration * 30_000))
        self._nchans = nchans
        self._t_step = t_step
        self._buffer = np.zeros((n_samples, nchans), dtype=np.int16)
        self._ts = np.zeros((n_samples,), dtype=np.int64)
        self._write_index = 0
        self._last_time = 0

    def handle_frame(self, pkt):
        if self._write_index < self._buffer.shape[0]:
            self._buffer[self._write_index, :] = memoryview(pkt.data[: self._nchans])
            self._ts[self._write_index] = pkt.header.time
            self._write_index += 1

    def finish(self):
        b_ts = self._ts > 0
        if np.any(b_ts):
            avg_isi = np.mean(np.diff(self._ts[b_ts]))
            ts_elapsed = self._ts[b_ts][-1] - self._ts[b_ts][0] + avg_isi
            s_elapsed = ts_elapsed * self._t_step
            n_samps = np.sum(b_ts)
            print(
                f"Collected {n_samps} samples in {s_elapsed} s\t({n_samps / s_elapsed:.2f} Hz)."
            )


def main(
    duration: float = 11.0,
    smpgroup: int = 6,
    nchans: int = 2,
    inst_addr: str = "",
    inst_port: int = 51002,
    client_addr: str = "",
    client_port: int = 51002,
    recv_bufsize: int = (8 if sys.platform == "win32" else 6) * 1024 * 1024,
    protocol: str = "4.1",
    loglevel: str = "debug",
):
    """
    Run the application:
    - Configure the connection to the nsp
    - Create an app, then register it is a callback that receives smp frames and updates internal state
    """
    # Handle logger arguments
    loglevel = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
    }[loglevel.lower()]
    logger.setLevel(loglevel)

    # Create connection to the device.
    params_obj = cbsdk.create_params(
        inst_addr=inst_addr,
        inst_port=inst_port,
        client_addr=client_addr,
        client_port=client_port,
        recv_bufsize=recv_bufsize,
        protocol=protocol,
    )
    nsp_obj = cbsdk.get_device(params_obj)
    if cbsdk.connect(nsp_obj, startup_sequence=True) != 50:
        logger.error(f"Could not connect to device with params {params_obj}")
        sys.exit(-1)
    config = cbsdk.get_config(nsp_obj)

    # Disable all channels
    for chtype in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]:
        cbsdk.set_all_channels_disable(nsp_obj, chtype)

    # Enable first nchans at smpgroup. For smpgroup < 5, this also updates the smpfilter.
    for ch in range(1, nchans + 1):
        _ = cbsdk.set_channel_config(nsp_obj, ch, "smpgroup", smpgroup)

    # Create a dummy app.
    t_step = 1 / (1e9 if config["b_gemini"] else config["sysfreq"])
    app = DummyApp(nchans, duration=duration, t_step=t_step)

    time.sleep(2.0)

    # Register callbacks to update the app's state when appropriate packets are received.
    _ = cbsdk.register_group_callback(nsp_obj, smpgroup, app.handle_frame)

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


if __name__ == "__main__":
    b_try_no_args = False
    try:
        import typer

        typer.run(main)
    except ModuleNotFoundError:
        print("Please install typer to use CLI args; using defaults.")
        b_try_no_args = True
    if b_try_no_args:
        main()
