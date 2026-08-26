import sys

if sys.platform != "win32":
    raise OSError("Windows-only module")

__version__ = "1.0.0"
