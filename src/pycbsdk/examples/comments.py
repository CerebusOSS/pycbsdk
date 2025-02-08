import sys
import logging
from pycbsdk import cbsdk


logger = logging.getLogger(__name__)


def handle_callback(comment_pkt):
    print(
        f"\nReceived comment {comment_pkt.comment} with timestamp {comment_pkt.timeStarted}\n"
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

    cbsdk.register_comment_callback(nsp_obj, handle_callback)

    try:
        while True:
            input("Press <enter> to start a new comment...")
            comment = input("Input comment: ")
            ts = nsp_obj.last_time
            print(f"Sending comment {comment} with timestamp {ts}")
            cbsdk.set_comment(nsp_obj, comment, ts)
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
