from .__version__ import __version__ as __version__
import warnings

warnings.warn(
    "pycbsdk (pure-Python) is deprecated and no longer maintained. "
    "Install the new CFFI-based pycbsdk from CereLink: "
    "pip install pycbsdk (the PyPI package has been replaced). "
    "See https://github.com/CerebusOSS/CereLink for details.",
    DeprecationWarning,
    stacklevel=2,
)
