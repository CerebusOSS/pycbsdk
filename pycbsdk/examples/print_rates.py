import sys
import argparse
import logging
from pycbsdk import cbsdk
import time
from collections import deque
import numpy as np


logger = logging.getLogger(__name__)


class DummyApp:
    spike_window = 0.5
    n_chans = 128

    def __init__(self):
        self._spike_times, self._spike_chans, self._spike_counts = None, None, None
        self._frames = None
        self.reset_state()

    def reset_state(self):
        # TODO: Get n_chans from device
        self._spike_times = [deque() for _ in range(DummyApp.n_chans)]
        self._spike_chans = deque()
        self._spike_counts = [0] * DummyApp.n_chans

    def update_state(self, spk_pkt):
        # If the file wrapped around then reset internal state.
        if self._spike_chans and (
            spk_pkt.header.time < self._spike_times[self._spike_chans[-1]][-1]
        ):
            self.reset_state()

        # Add new spike events
        self._spike_times[spk_pkt.header.chid].append(spk_pkt.header.time)
        self._spike_chans.append(spk_pkt.header.chid)
        self._spike_counts[spk_pkt.header.chid] += 1

        # Clear old spike events
        cutoff = spk_pkt.header.time - round(30000 * DummyApp.spike_window)
        while self._spike_chans and self._spike_times[self._spike_chans[0]][0] < cutoff:
            rem_chid = self._spike_chans.popleft()
            self._spike_times[rem_chid].popleft()
            self._spike_counts[rem_chid] -= 1

    def handle_frame(self, pkt):
        if self._frames is None or self._frames.shape[1] != pkt.data.size:
            # First packet or first packet of new shape.
            self._frames = pkt.data[None, :]
        else:
            self._frames = np.vstack((self._frames, pkt.data))
        if self._frames.shape[0] > 30000:
            res = ",\t".join(
                [
                    f"{mu:.2f} +/- {sigma:.2f}"
                    for mu, sigma in zip(
                        np.mean(self._frames, axis=0), np.std(self._frames, axis=0)
                    )
                ]
            )
            print(res)
            self._frames = self._frames[-1:, :]

    def render_state(self):
        print(
            f"Firing rate:\t{np.nanmean(self._spike_counts) / DummyApp.spike_window:.2f} Hz "
            f"+/- {np.nanstd(self._spike_counts) / DummyApp.spike_window:.2f} "  # Not sure if valid?
            f"({np.nanmin(self._spike_counts) / DummyApp.spike_window:.2f} - {np.nanmax(self._spike_counts) / DummyApp.spike_window:.2f})"
        )


def run(skip_startup: bool = False, **params_kwargs):
    """
    Run the application:
    - setup the connection to the nsp
    - register a callback that handles the spikes and updates internal state
    - run the async chain
    - on the main thread, render the internal state (print the min-max mean+/-std of the rates every 0.5 seconds).
    :param skip_startup:
    :return:
    """
    params_obj = cbsdk.create_params(**params_kwargs)
    nsp_obj = cbsdk.get_device(params_obj)
    run_level = cbsdk.connect(nsp_obj, startup_sequence=not skip_startup)
    if not run_level:
        logger.error(f"Could not connect to device. Check params and try again: \n{params_obj}.")
        return
    config = cbsdk.get_config(nsp_obj)

    # Check which channels have spiking enabled and what kind of thresholding they are using.
    #  TODO: We should have API functions to check channel capabilities instead of
    #   importing from pycbsdk.cbhw and doing bitwise testing here
    from pycbsdk.cbhw.device.nsp import CBAInpSpk
    from pycbsdk.cbhw.packet.common import CBChannelType

    spike_status = {"auto": set(), "manual": set(), "disabled": set()}
    for chid in [
        k for k, v in config["channel_types"].items() if v == CBChannelType.FrontEnd
    ]:
        pkt = config["channel_infos"][chid]
        if pkt.spkopts & CBAInpSpk.EXTRACT.value:
            if pkt.spkopts & CBAInpSpk.THRAUTO.value:
                spike_status["auto"].add(chid)
            else:
                spike_status["manual"].add(chid)
        else:
            spike_status["disabled"].add(chid)
    print(
        f"Found {len(spike_status['auto']) + len(spike_status['manual'])} channels with spiking enabled "
        f"and {len(spike_status['disabled'])} with spiking disabled."
    )
    print(
        f"{len(spike_status['auto'])} of the spike-enabled channels are using auto-thresholding."
    )

    if not skip_startup:
        # Disable spiking on all front end channels.
        for chid in [
            k
            for k, v in config["channel_types"].items()
            if v in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]
        ]:
            _ = cbsdk.set_channel_spk_config(nsp_obj, chid, "enable", False)
            _ = cbsdk.set_channel_config(nsp_obj, chid, "smpgroup", 0)

        # Enable some channels for spiking and sample group 5
        N_ACTIVE_CHANNELS = 3
        for chid in range(1, 1 + N_ACTIVE_CHANNELS):
            _ = cbsdk.set_channel_spk_config(nsp_obj, chid, "enable", True)
            _ = cbsdk.set_channel_spk_config(nsp_obj, chid, "autothreshold", True)
            _ = cbsdk.set_channel_config(nsp_obj, chid, "smpgroup", 5)

    # Create a dummy app.
    app = DummyApp()
    # Register callbacks to update the app's state when appropriate packets are received.
    _ = cbsdk.register_spk_callback(nsp_obj, app.update_state)
    _ = cbsdk.register_group_callback(nsp_obj, 5, app.handle_frame)

    # DEBUG: Register a callback to print the heartbeat.
    # _ = cbsdk.register_config_callback(nsp_obj, packet.CBPacketType.SYSHEARTBEAT,
    #                                      lambda pkt: print(f"Heartbeat proctime: {pkt.header.time}"))

    # Render the internal state forever. Here this is simply a printout. It could be a GUI or a BCI.
    try:
        while True:
            app.render_state()
            time.sleep(5.0)
    except KeyboardInterrupt:
        pass
    finally:
        _ = cbsdk.disconnect(nsp_obj)


def main():
    # --inst_addr=192.168.137.255 --client_addr=192.168.137.199
    parser = argparse.ArgumentParser(description="Consume data from (emulated) NSP.")
    parser.add_argument(
        "--inst_addr",
        "-i",
        type=str,
        default="",
        help="ipv4 address of device. pycbsdk will send control packets to this address. Subnet OK. "
        "Use 127.0.0.1 for use with nPlayServer (non-bcast). "
        "The default is 0.0.0.0 (IPADDR_ANY) on Mac and Linux. On Windows, known IPs will be searched."
        ,
    )
    parser.add_argument("--inst_port", type=int, default=51002, help="Network port to send control packets."
                                                                     "Use 51002 for Gemini and 51001 for Legacy NSP.")
    parser.add_argument(
        "--client_addr",
        "-c",
        type=str,
        default="",
        help="ipv4 address of this machine's network adapter we will receive packets on. "
        "Defaults to INADDR_ANY. If address is provided, assumes Cerebus Subnet.",
    )
    parser.add_argument("--client_port", "-p", type=int, default=51002, help="Network port to receive packets. This should always be 51002.")
    parser.add_argument(
        "--recv_bufsize",
        "-b",
        type=int,
        help=f"UDP socket recv buffer size. "
        f"Default: {(8 if sys.platform == 'win32' else 6) * 1024 * 1024}.",
    )
    parser.add_argument("--protocol", type=str, default="4.1", help="Protocol Version. 3.11, 4.0, or 4.1 supported.")
    parser.add_argument("--skip_startup", action="store_true", help="Skip the initial handshake as well as the attempt to set the device to RUNNING.")
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
