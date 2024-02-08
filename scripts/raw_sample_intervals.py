import sys
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
            mean_itsi = np.mean(np.diff(self._ts[b_ts]))
            ts_elapsed = self._ts[b_ts][-1] - self._ts[b_ts][0]
            if mean_itsi < 100:
                s_elapsed = ts_elapsed / 30_000
            else:
                # If timestamps are nanoseconds then mean_itsi should be ~ 33_333
                s_elapsed = ts_elapsed / 1e9
            s_elapsed += 1 / 30_000
            n_samps = np.sum(b_ts)
            print(
                f"Collected {n_samps} samples in {s_elapsed} s\t({n_samps/s_elapsed:.2f} Hz)."
            )


def main(
    duration: float = 11.0,
    smpgroup: int = 6,
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

    # Disable all channels spike and continuous.
    #  Note: Setting smpgroup=0 will also disable raw.
    #  Note: Setting any smpgroup also disables filters. :/
    for chid in [
        k
        for k, v in config["channel_types"].items()
        if v in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]
    ]:
        _ = cbsdk.set_channel_spk_config(nsp_obj, chid, "enable", False)
        _ = cbsdk.set_channel_config(nsp_obj, chid, "smpgroup", 0)

    # Enable channel 1 at smpgroup.
    _ = cbsdk.set_channel_config(nsp_obj, 1, "smpgroup", smpgroup)

    # Create a dummy app.
    app = DummyApp(duration=duration)

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
