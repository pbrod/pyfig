import sys

if sys.platform != "win32":
    raise OSError("Windows-only module")

from functools import wraps

from .testing import test as _test  # noqa

__version__ = "1.0.1"


@wraps(_test)
def test(*options: str) -> int:
    return _test(__name__, *options)
