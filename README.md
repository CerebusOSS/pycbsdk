[![PyPI version](https://badge.fury.io/py/pycbsdk.svg)](https://badge.fury.io/py/pycbsdk)

# pycbsdk

Pure Python package for communicating with Blackrock Cerebus devices

## Quick Start

From a shell...

```shell
pip install pycbsdk
```

Then in python

```Python
from pycbsdk import cbsdk


params_obj = cbsdk.create_params()
nsp_obj = cbsdk.get_device(params_obj)
err = cbsdk.connect(nsp_obj)
config = cbsdk.get_config(nsp_obj)
print(config)
```

You may also try the provided test script with `python -m pycbsdk.examples.print_rates` or via the shortcut: `pycbsdk_print_rates`.

## Introduction

`pycbsdk` is a pure Python package for communicating with a Blackrock Neurotech Cerebus device. It is loosely based on Blackrock's `cbsdk`, but shares no code nor is `pycbsdk` supported by Blackrock.

`pycbsdk`'s API design is intended to mimic that of a C-library. Indeed, a primary goal of this library is to help prototype libraries in other languages. After all, Python is a poor choice to handle high throughput data without some compiled language underneath doing all the heavy lifting.

However, it's pretty useful as is! And so far it has been good-enough for some quick test scripts, and it even drops fewer packets than CereLink. So, please use it, and contribute! We are more than happy to see the API expand to support more features, or even to have an additional "pythonic" API.

## Design

When the connection to the device is established, two threads are created and started:
* `CerebusDatagramThread`
  * Retrieves datagrams using `asyncio`
  * Slices into generic packets
  * Casts packets into their native type
  * Enqueues packets for the PacketHandlerThread
* `PacketHandlerThread`
  * Updates device state (e.g., mirrors device time)
  * Calls registered callbacks depending on the packet type.

The device also registers some of its own internal callbacks to monitor config state.

The client can use API functions to:
* Get / Set config -- these might simply grab the internal state or they might warrant a roundtrip communication to the device.
  * The latter may hold back the return value until the reply packet has been received and can therefore be slow. Try to call `get_config` with `force_refresh=True` sparingly.
* Register a callback to receive data as soon as it appears on the handler thread.
  
This and more should appear in the documentation at some point in the future...

## Limitations

* This library takes exclusive control over the UDP socket on port 51002 and thus cannot be used with Central, nor any other instance of `pycbsdk`. You only get one instance of `pycbsdk` _or_ Central per machine.
* The API is still very sparse and limited in functionality.
* For now, Python still has the GIL. This means that despite using threading, if your callback functions are slow and hold up the PacketHandlerThread, this could hold up datagram retrieval and ultimately cause packets to be dropped.
  * A possible solution is for your callbacks to simply enqueue the data for a longer-running process to handle.
