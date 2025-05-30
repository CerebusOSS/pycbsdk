import sys
import logging
from pycbsdk import cbsdk
import time
from collections import deque
import numpy as np


logger = logging.getLogger(__name__)


class DummyApp:
    def __init__(self, n_chans, history=1.0, tstep=(1 / 30_000)):
        self._n_chans = n_chans
        self._hist_dur = history
        self._cutoff_steps = round(self._hist_dur / tstep)
        self._spike_times, self._spike_chans, self._spike_counts = None, None, None
        self._frames = None
        self.reset_state()

    def reset_state(self):
        # Time of spike events in order received.
        self._spike_times = deque()
        # Channel of spike event in order received.
        self._spike_chans = deque()
        # Number of spikes in buffer for each channel:
        self._spike_counts = [0] * self._n_chans

    def update_state(self, spk_pkt):
        # Packet header chid is 1-based. We need a 0-based for indexing.
        chix = spk_pkt.header.chid - 1

        # Add new spike events
        self._spike_times.append(spk_pkt.header.time)
        self._spike_chans.append(spk_pkt.header.chid)
        self._spike_counts[chix] += 1

        # Clear old spike events
        cutoff = spk_pkt.header.time - self._cutoff_steps
        while self._spike_chans and (
            (self._spike_times[0] < cutoff)
            or (self._spike_times[0] > self._spike_times[-1])
        ):
            rem_chix = self._spike_chans.popleft() - 1
            self._spike_times.popleft()
            self._spike_counts[rem_chix] -= 1

    def render_state(self):
        print(
            f"Firing rate:\t{np.nanmean(self._spike_counts) / self._hist_dur:.2f} Hz "
            f"+/- {np.nanstd(self._spike_counts) / self._hist_dur:.2f} "  # Not sure if valid?
            f"({np.nanmin(self._spike_counts) / self._hist_dur:.2f} - {np.nanmax(self._spike_counts) / self._hist_dur:.2f})"
        )


def main(
    inst_addr: str = "",
    inst_port: int = 51002,
    client_addr: str = "",
    client_port: int = 51002,
    recv_bufsize: int = (8 if sys.platform == "win32" else 6) * 1024 * 1024,
    protocol: str = "4.1",
    loglevel: str = "debug",
    skip_startup: bool = False,
    update_interval: float = 1.0,
    set_hoops: bool = False,
):
    """
    Run the application:
    - Set up the connection to the nsp.
    - Normalize the device config (disable all continuous, activate spiking with man. thresh on all channels).
    - Create a dummy application.
    - Use the app to register a callback that handles the spikes and updates internal state.
    - The app will render its internal state (summary spike rate statistics).
    :param inst_addr: ipv4 address of device. pycbsdk will send control packets to this address.
        Use 127.0.0.1 for use with nPlayServer (non-bcast).
        Subnet OK, e.g. 192.168.137.255 well send control packets to all devices on subnet.
        The default is 0.0.0.0 (IPADDR_ANY) on Mac and Linux. On Windows, known IPs will be searched.
    :param inst_port: Network port to send control packets.
        Use 51002 for Gemini and 51001 for Legacy NSP.
    :param client_addr: ipv4 address of this machine's network adapter we will receive packets on.
        Defaults to INADDR_ANY. If address is provided, assumes Cerebus Subnet.
    :param client_port:
        Network port to receive packets. This should always be 51002.
    :param recv_bufsize: UDP socket recv buffer size.
    :param protocol: Protocol Version. 3.11, 4.0, or 4.1 supported.
    :param loglevel: debug, info, or warning
    :param skip_startup: Skip the initial handshake as well as the attempt to set the device to RUNNING.
    :param update_interval: Interval between updates. This determines how big the queues can grow.
    :param set_hoops: set True to enable hoop-based sorting on channel 2.
    :return:
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
    if cbsdk.connect(nsp_obj, startup_sequence=not skip_startup) != 50:
        logger.error(
            f"Could not connect to device. Check params and try again: \n{params_obj}."
        )
        sys.exit(-1)

    config = cbsdk.get_config(nsp_obj)
    if not config:
        sys.exit(-1)

    # Note: config["channel_types"] and config["channel_infos"] are both dictionaries
    #  where the keys are 1-based channel indices.

    # Print information about current config.
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

    # Enable spiking and disable continuous streams on all analog channels
    for ch_type in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]:
        cbsdk.set_all_channels_disable(nsp_obj, ch_type)
        cbsdk.set_all_channels_spk_config(nsp_obj, ch_type, "enable", True)

    if set_hoops:
        spk_hoops = {
            1: {
                1: {"time": 13, "min": -975, "max": -646},
                2: {"time": 6, "min": 108, "max": 342},
            },
            2: {
                1: {"time": 21, "min": 675, "max": 1033},
                2: {"time": 31, "min": -538, "max": -185},
            },
            3: {
                1: {"time": 17, "min": 481, "max": 820},
                2: {"time": 35, "min": -23, "max": 262},
            },
        }
        cbsdk.set_channel_spk_config(nsp_obj, 2, "hoops", spk_hoops)

    # Count the number of FrontEnd | AnalogIn channels.
    b_spk = [
        _ in [CBChannelType.FrontEnd, CBChannelType.AnalogIn]
        for _ in config["channel_types"].values()
    ]
    n_chans = sum(b_spk)

    # Calculate the clock step (I hate this)
    if inst_addr and int(inst_addr.split(".")[-1]) in [200, 201, 202, 203, 203]:
        # Note: This misses Gemini NSP!
        t_step = 1 / 1e9
    else:
        t_step = 1 / config["sysfreq"]

    # Create the dummy app.
    app = DummyApp(n_chans, history=update_interval, tstep=t_step)
    # Register callbacks to update the app's state when appropriate packets are received.
    _ = cbsdk.register_spk_callback(nsp_obj, app.update_state)

    # DEBUG: Register a callback to print the heartbeat.
    # _ = cbsdk.register_config_callback(nsp_obj, packet.CBPacketType.SYSHEARTBEAT,
    #                                      lambda pkt: print(f"Heartbeat proctime: {pkt.header.time}"))

    # Render the internal state forever. Here this is simply a printout. It could be a GUI or a BCI.
    # Ctrl + C to quit.
    try:
        while True:
            app.render_state()
            time.sleep(update_interval)
    except KeyboardInterrupt:
        pass
    finally:
        _ = cbsdk.disconnect(nsp_obj)


if __name__ == "__main__":
    b_try_with_defaults = False
    try:
        import typer

        typer.run(main)
    except ModuleNotFoundError:
        print(
            "`pip install typer` to pass command-line arguments. Trying with defaults."
        )
        b_try_with_defaults = True
    if b_try_with_defaults:
        main()
