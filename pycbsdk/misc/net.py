import platform
import subprocess


def ping(host: str) -> bool:
    p = platform.platform().lower()
    if "mac" in p:
        n = "-c"
        succ_str = "1 packets received"
    else:
        n = "-n"
        succ_str = f"Reply from {host}"
    process = subprocess.Popen(
        ["ping", n, "1", host], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    streamdata = process.communicate()[0]
    return succ_str in str(streamdata)
