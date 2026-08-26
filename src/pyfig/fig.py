# /usr/bin/env python
# -*- coding: utf-8 -*-
"""
FIG — Figure/Window Manipulation Utilities (Windows-only)

This module provides tools for manipulating Matplotlib, TVTK, and Chaco
figure windows on **Windows**, using the Win32 API. It supports:

- Maximizing, minimizing, restoring, hiding windows
- Cascading, tiling, stacking, and piling windows
- Center, snap_left, snap_right, snap_top and snap_bottom windows
- Selecting subsets of windows to keep or close
- Cycling through windows (wxPython dialog with console fallback)
- Getting figure window geometry (position, size, screen area)
- Finding figure numbers and their window handles by examining window titles

Refactor Highlights
-------------------
This is a **fully refactored version** of the original `fig.py`, with:

1. A new **WindowManager** object-oriented architecture
2. Safer, cleaner, more deterministic
3. Safe wrappers around all Win32 calls
4. Fully rewritten, modern **NumPy-style docstrings**
5. Backward-compatible procedural functions (`fig.close()`, `fig.tile()`, ...)
6. Support for wxPython-based figure cycling when available.

wxPython Support
----------------
FIG_USE_WX:
    If enabled and wxPython is available, use the
    wx-based cycling dialog. Otherwise use the
    console-based cycling interface.


Configuration
-------------
Environment variable:

    FIG_USE_WX=1   # prefer wxPython cycling dialog
    FIG_USE_WX=0   # use console-based cycling (default)

Programmatic:

    import fig
    fig.set_prefer_wx(False)

Public API
----------
cascade, center, pile,  stack, tile,
snap_left, snap_right, snap_top, snap_bottom
close, cycle, hide, keep, maximize, minimize,
restore, set_size,
find_all_figure_numbers, find_figure_handles,
get_window_position_and_size, get_screen_position_and_size

NOTE: Importing this module on non-Windows systems raises OSError.

Examples
--------
>>> import matplotlib.pyplot as plt
>>> import fig
>>> for ix in range(6):
...     f = plt.figure(ix)
>>> fig.stack('all')
>>> fig.stack(1,2)
>>> fig.hide(1)
>>> fig.restore(1)
>>> fig.tile()
>>> fig.pile()
>>> fig.maximize(4)
>>> fig.close('all')
"""

# ======================================================================
# Imports
# ======================================================================
from __future__ import annotations

import os
import sys
import time
import logging
import re


from collections.abc import Callable, Iterable, Iterator, Sequence
from functools import wraps
from logging import Logger
from typing import Any, Literal


# ---------------- OS Guard --------------------------------------------
if sys.platform != "win32":
    raise OSError("Windows-only module")


# ---------------- Win32 API -------------------------------------------
try:
    import win32gui
    import win32con
    import win32api
except ImportError as exc:
    raise ImportError(
        "pywin32 is required"
    ) from exc


# ---------------- Optional wxPython -----------------------------------
try:
    import wx
except ImportError:
    wx = None

import numpy as _np

# typehint aliases
FigureNumber = int
FigureArg = FigureNumber | str | Iterable[int | str]
Handle = int
Interval = float | Literal["user_defined"]
Position = tuple[int, int]
Rect = tuple[int, int, int, int]  # x, y, width, height

# ======================================================================
# Logging
# ======================================================================

_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

# ======================================================================
# Constants
# ======================================================================

FIGURE_TITLE_FORMATS = ("Figure", "TVTK Scene", "Chaco Plot Window: Figure")
__all__ = [
    "cascade",
    "center",
    "pile",
    "stack",
    "tile",
    "snap_left",
    "snap_right",
    "snap_top",
    "snap_bottom",
    "close",
    "cycle",
    "hide",
    "keep",
    "maximize",
    "minimize",
    "restore",
    "find_all_figure_numbers",
    "find_figure_handles",
    "set_size",
    "get_window_position_and_size",
    "get_screen_position_and_size",
    "set_prefer_wx",
    "WindowManager",
]

_DEFAULT_USE_WX = (
    os.environ.get("FIG_USE_WX", "0")
    .strip()
    .lower()
    not in {"0", "false", ""}
)


# ======================================================================
# Low-Level Safe Win32 Wrappers
# ======================================================================


def _safe_call(
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any | None:
    """Safely call a Win32 API function, swallowing `win32gui.error`.

    Parameters
    ----------
    fn : callable
        Win32 API function to call.
    *args : tuple
        Positional arguments to pass to the function.
    **kwargs : dict
        Keyword arguments to pass to the function.

    Returns
    -------
    object or None
        Return value from the Win32 API call, or None if it failed.
    """
    try:
        return fn(*args, **kwargs)
    except win32gui.error:
        _logger.debug("Win32 API call failed: %s(%s, %s)", fn, args, kwargs)
        return None


def _is_window(handle: Handle) -> bool:
    """Check whether a window handle corresponds to a visible window.

    Parameters
    ----------
    handle : int
        Window handle.

    Returns
    -------
    bool
        True if the handle is valid and visible.
    """
    try:
        return bool(win32gui.IsWindow(handle)) and bool(
            win32gui.IsWindowVisible(handle)
        )
    except win32gui.error:
        return False


def _enum_windows() -> list[tuple[Handle, str]]:
    """Enumerate all visible top-level windows.

    Returns
    -------
    list of (int, str)
        Window handles and their titles.
    """
    result: list[tuple[Handle, str]] = []

    def _callback(
        h: Handle,
        out: list[tuple[Handle, str]],
    ) -> None:
        if win32gui.IsWindowVisible(h):
            try:
                title = win32gui.GetWindowText(h)
            except win32gui.error:
                title = ""
            out.append((h, title))

    _safe_call(win32gui.EnumWindows, _callback, result)
    return result


def _move_window(
    handle: Handle,
    x: int,
    y: int,
    w: int,
    h: int,
    redraw: bool = True,
) -> None:
    _safe_call(win32gui.MoveWindow, handle, x, y, w, h, int(bool(redraw)))


def _show_window(
    handle: Handle,
    command: int,
) -> None:
    _safe_call(win32gui.ShowWindow, handle, command)


def _bring_to_top(handle: Handle) -> None:
    _safe_call(win32gui.BringWindowToTop, handle)


def _get_window_rect(
    handle: Handle,
) -> tuple[int, int, int, int] | None:
    try:
        return win32gui.GetWindowRect(handle)
    except win32gui.error:
        return None


def _redraw_window_now(handle: Handle) -> None:
    rect = _get_window_rect(handle)
    if rect:
        _safe_call(win32gui.RedrawWindow, handle, rect, None, win32con.RDW_UPDATENOW)


def _monitor_work_area(
    handle: Handle,
) -> Rect:
    monitor = win32api.MonitorFromWindow(
        handle,
        win32con.MONITOR_DEFAULTTONEAREST,
    )
    info = win32api.GetMonitorInfo(monitor)
    left, top, right, bottom = info["Work"]
    width, height = right - left, bottom - top
    return left, top, width, height

# ======================================================================
# WindowManager — Core OOP Engine
# ======================================================================


class WindowManager:
    """
    Manage figure windows for Matplotlib/TVTK/Chaco using the Win32 API.

    This class provides all figure-window manipulation operations. Procedural
    functions in this module delegate to a global instance of this class.

    Parameters
    ----------
    prefer_wx : bool, optional
        If True and wxPython is available, use the wx-based
        cycling dialog. Otherwise use the console interface.
    title_formats : sequence of str, optional
        String prefixes used to identify figure windows by title.
    logger : logging.Logger, optional
        Logger instance for reporting errors and debug messages.

    """
    def __init__(
        self,
        prefer_wx: bool = True,
        title_formats: Sequence[str] = FIGURE_TITLE_FORMATS,
        logger: Logger | None = None,
    ) -> None:
        self.prefer_wx = bool(prefer_wx)
        self.title_formats = tuple(title_formats)
        self.log = logger or _logger
        titles = "|".join(
            re.escape(s)
            for s in self.title_formats
        )
        self._figure_re = re.compile(rf"^(?:{titles})\s+(\d+)(?:\D.*)?$")

    # ------------------------------------------------------------------
    # Figure Discovery
    # ------------------------------------------------------------------

    def find_figure_handles(
        self,
        *figure_numbers: FigureArg,
    ) -> list[Handle]:
        """
        Return Win32 window handles for the given figure numbers.

        Parameters
        ----------
        *figure_numbers : int or sequence of int or 'all'
            Identifiers of figures to locate. If no numbers are provided,
            all known figure numbers are used.

        Returns
        -------
        list of int
            Valid window handles for the requested figure numbers.

        Notes
        -----
        Figure windows are identified by scanning their titles using the
        prefixes listed in `title_formats`.
        """
        wanted = set(self._parse_figure_numbers(*figure_numbers))

        handles = []

        for h, title in _enum_windows():
            m = self._figure_re.match(title)
            if m and int(m.group(1)) in wanted:
                handles.append(h)

        return handles

    def find_all_figure_numbers(
        self,
    ) -> list[FigureNumber]:
        """
        Return all detected figure numbers.

        Returns
        -------
        list of int
            Unique figure numbers found among visible windows.

        Examples
        --------
        >>> import fig
        >>> import matplotlib.pyplot as plt
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        ...     plt.draw()
        >>> plt.pause(0.1)  # add plt.pause to allow event handlers to catch up

        fig.find_all_figure_numbers()
        [0, 1, 2, 3, 4]

        >>> fig.close()
        """

        out = []
        windows = _enum_windows()

        for _, title in windows:
            m = self._figure_re.match(title)
            if m:
                out.append(int(m.group(1)))

        return sorted(set(out))

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @staticmethod
    def get_window_position_and_size(
        handle: Handle,
    ) -> Rect:
        """
        Return window position and size.

        Parameters
        ----------
        handle : int
            Window handle.

        Returns
        -------
        (int, int, int, int)
            (x, y, width, height), or zeros if the window is invalid.
        """
        rect = _get_window_rect(handle)
        if not rect:
            return (0, 0, 0, 0)
        x, y, right, bottom = rect
        return (x, y, max(0, right - x), max(0, bottom - y))

    def get_screen_position_and_size(
        self,
        handles: Sequence[Handle],
    ) -> Rect:
        """
        Return the position and size of the screen containing the windows.

        Parameters
        ----------
        handles : sequence of int
            Window handles used as probes for determining screen geometry.

        Returns
        -------
        (int, int, int, int)
            (x, y, width, height) representing the work area of the
            monitor containing the first valid window handle.
        """
        handle = next((h for h in handles if _is_window(h)), None)
        if handle is None:
            return (0, 0, 0, 0)

        try:
            return _monitor_work_area(handle)
        except (win32gui.error, win32api.error) as exc:
            self.log.debug("Unable to obtain monitor information: %s", exc)
            return (0, 0, 0, 0)

    # ------------------------------------------------------------------
    # Utility Parsing
    # ------------------------------------------------------------------
    def _parse_figure_numbers(
        self,
        *args: object,
    ) -> list[FigureNumber]:
        """
        Convert figure number arguments into a resolved list of integers.

        Parameters
        ----------
        *args : int, sequence of int, or 'all'
            Arguments specifying figure numbers.

        Returns
        -------
        list of int
            Flattened and resolved list of figure numbers.

        Notes
        -----
        Legacy behavior: if no identifiers are given, interpret this as
        “all open figures.”
        """
        def flatten(obj: object) -> Iterator[object]:
            if isinstance(obj, str):
                yield obj
                return

            if isinstance(obj, Iterable):
                for item in obj:
                    yield from flatten(item)
            else:
                yield obj

        out: list[FigureNumber] = []

        for arg in flatten(args):
            if arg == "all":
                return self.find_all_figure_numbers()

            if arg is None:
                continue

            try:
                out.append(int(arg))
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"Invalid figure identifier: {arg!r}"
                ) from exc

        return out or self.find_all_figure_numbers()

    # ------------------------------------------------------------------
    # High-Level Manipulators
    # ------------------------------------------------------------------

    def keep(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Keep only the specified figures and close all others.

        Parameters
        ----------
        figure_numbers : list of integers specifying which figures to keep.

        Examples
        --------
        # keep only figures 1,2,3,5 and 7
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(10):
        ...     f = plt.figure(ix)
        >>> fig.keep(list(range(1,4)),  5, 7)

        or
            fig.keep([range(1,4),  5, 7])
        >>> fig.close()

        See also
        --------
        fig.close

        """
        keepers = set(self._parse_figure_numbers(*figure_numbers))
        allfigs = set(self.find_all_figure_numbers())
        to_close = list(allfigs.difference(keepers))
        self.close(*to_close)

    def close(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Close figure windows.

        Parameters
        ----------
        *figure_numbers : int, sequence of int, or 'all'
            Identifiers of figures to close. If omitted, closes all figures.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        >>> fig.close(3,4)   # close figure 3 and 4
        >>> fig.close('all') # close all remaining figures

        or even simpler
        fig.close() # close all remaining figures

        See also
        --------
        fig.keep

        """
        numbers = self._parse_figure_numbers(*figure_numbers)

        # First try matplotlib close
        try:
            import matplotlib.pyplot as plt

            for num in numbers:
                try:
                    plt.close(int(num))
                except Exception:
                    pass

            plt.pause(0.05)

        except Exception:
            pass

        # Polite Win32 close
        for h in self.find_figure_handles(*numbers):
            _safe_call(
                win32gui.PostMessage,
                h,
                win32con.WM_CLOSE,
                0,
                0,
            )

        time.sleep(0.05)

        # Last resort force close
        for h in self.find_figure_handles(*numbers):
            _safe_call(win32gui.DestroyWindow, h)

    def restore(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Restore figure windows to their previous size and position.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to restore (default 'all').

        Description
        -----------
        RESTORE Activates and displays the window. If the window is minimized
        or maximized, the system restores it to its original size and position.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        >>> fig.restore('all')   # Restores all figures
        >>> fig.restore()        # same as restore('all')
        >>> fig.restore(plt.gcf().number)  # Restores the current figure
        >>> fig.restore(3)       # Restores figure 3
        >>> fig.restore([2, 4])  # Restores figures 2 and 4

            or alternatively
            fig.restore(2, 4)
        >>> fig.close()

        See also
        --------
        fig.close,
        fig.keep

        """
        self._show_figs(
            self._parse_figure_numbers(*figure_numbers), win32con.SW_RESTORE
        )

    def hide(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        hide figure windows.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to hide (default 'all').

        Examples
        --------
        >>> import fig
        >>> import matplotlib.pyplot as plt
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        >>> fig.hide('all')   # hides all unhidden figures
        >>> fig.hide()        # same as hide('all')
        >>> fig.hide(plt.gcf().number)  # hides the current figure
        >>> fig.hide(3)        # hides figure 3
        >>> fig.hide([2, 4])   # hides figures 2 and 4

        or alternatively
            fig.hide(2, 4)
        >>> fig.restore(list(range(5)))
        >>> fig.close()

        See also
        --------
        fig.cycle,
        fig.keep,
        fig.restore

        """
        self._show_figs(self._parse_figure_numbers(*figure_numbers), win32con.SW_HIDE)

    def cascade(
        self,
        *figure_numbers: FigureArg,
        width: int | None = None,
        height: int | None = None,
        x_step: int = 30,
        y_step: int = 30,
    ) -> None:
        """
        Arrange figure windows in a cascading layout.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to cascade.
        width : int, optional
            Width of each cascaded window. Defaults to a fraction of the
            available screen width.
        height : int, optional
            Height of each cascaded window. Defaults to a fraction of the
            available screen height.
        x_step : int, optional
            Horizontal offset between successive windows.
        y_step : int, optional
            Vertical offset between successive windows.

        Returns
        -------
        None

        Notes
        -----
        Windows are resized to a common size and positioned with a fixed
        horizontal and vertical offset relative to the previous window.
        This creates the classic Windows "cascade" appearance.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(6):
        ...     _ = plt.figure(ix)
        >>> fig.cascade()

        Cascade selected figures:

        >>> fig.cascade([1, 2, 3], width=800, height=600)

        See also
        --------
        fig.stack,
        fig.pile,
        fig.tile,
        fig.center
        """
        handles = self.find_figure_handles(*figure_numbers)
        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        if width is None:
            width = int(sw * 0.7)

        if height is None:
            height = int(sh * 0.7)

        for i, h in enumerate(handles):
            x = sx + (i * x_step) % max(1, sw - width)
            y = sy + (i * y_step) % max(1, sh - height)

            _move_window(h, x, y, width, height, True)
            _bring_to_top(h)

    def center(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Center figure windows on the screen.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to center. If omitted, all figures are centered.

        Returns
        -------
        None

        Notes
        -----
        Window sizes are preserved. Each selected figure is moved so that
        its center coincides with the center of the available screen area.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(3):
        ...     _ = plt.figure(ix)
        >>> fig.center()

        Center a specific figure:

        >>> fig.center(1)

        Center multiple figures:

        >>> fig.center([1, 2])

        See also
        --------
        fig.set_size,
        fig.cascade,
        fig.snap_left,
        fig.snap_right
        """
        handles = self.find_figure_handles(*figure_numbers)

        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        for h in handles:
            _, _, width, height = self.get_window_position_and_size(h)

            x = sx + (sw - width) // 2
            y = sy + (sh - height) // 2

            _move_window(h, x, y, width, height, True)
            _bring_to_top(h)

    def snap_top(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Snap figure windows to the upper half of the screen.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to snap. If omitted, all figures are snapped.

        Returns
        -------
        None

        Notes
        -----
        Selected windows are resized and positioned to occupy the upper half
        of the available screen area. This operation is similar to the
        vertical half-screen snapping available in modern desktop
        environments.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(4):
        ...     _ = plt.figure(ix)
        >>> fig.snap_top()

        Snap selected figures:

        >>> fig.snap_top([1, 2])

        See also
        --------
        fig.snap_bottom,
        fig.snap_left,
        fig.snap_right,
        fig.tile
        """
        handles = self.find_figure_handles(*figure_numbers)

        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        height = sh // 2

        for h in handles:
            _move_window(
                h,
                sx,
                sy,
                sw,
                height,
                True,
            )
            _bring_to_top(h)

    def snap_left(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Snap figure windows to the left half of the screen.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to snap. If omitted, all figures are snapped.

        Returns
        -------
        None

        Notes
        -----
        Selected windows are resized and positioned to occupy the left half
        of the available screen area. This operation is similar to pressing
        ``Win + Left Arrow`` in Microsoft Windows.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(4):
        ...     _ = plt.figure(ix)
        >>> fig.snap_left()

        Snap selected figures:

        >>> fig.snap_left([1, 2])

        See also
        --------
        fig.snap_right,
        fig.tile,
        fig.maximize
        """
        handles = self.find_figure_handles(*figure_numbers)

        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        width = sw // 2

        for h in handles:
            _move_window(h, sx, sy, width, sh, True)
            _bring_to_top(h)

    def snap_right(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Snap figure windows to the right half of the screen.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to snap. If omitted, all figures are snapped.

        Returns
        -------
        None

        Notes
        -----
        Selected windows are resized and positioned to occupy the right half
        of the available screen area. This operation is similar to pressing
        ``Win + Right Arrow`` in Microsoft Windows.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(4):
        ...     _ = plt.figure(ix)
        >>> fig.snap_right()

        Snap selected figures:

        >>> fig.snap_right(3)

        See also
        --------
        fig.snap_left,
        fig.tile,
        fig.maximize
        """
        handles = self.find_figure_handles(*figure_numbers)

        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        width = sw // 2

        for h in handles:
            _move_window(
                h,
                sx + width,
                sy,
                sw - width,
                sh,
                True,
            )
            _bring_to_top(h)

    def snap_bottom(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Snap figure windows to the lower half of the screen.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to snap. If omitted, all figures are snapped.

        Returns
        -------
        None

        Notes
        -----
        Selected windows are resized and positioned to occupy the lower half
        of the available screen area. This operation complements
        ``snap_top()`` and enables quick vertical window arrangements.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(4):
        ...     _ = plt.figure(ix)
        >>> fig.snap_bottom()

        Snap a specific figure:

        >>> fig.snap_bottom(3)

        See also
        --------
        fig.snap_top,
        fig.snap_left,
        fig.snap_right,
        fig.tile
        """
        handles = self.find_figure_handles(*figure_numbers)

        if not handles:
            return

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)

        height = sh // 2

        for h in handles:
            _move_window(
                h,
                sx,
                sy + height,
                sw,
                sh - height,
                True,
            )
            _bring_to_top(h)

    def minimize(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Minimize figure windows.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to minimize (default 'all').

        Examples
        --------
        >>> import fig
        >>> import matplotlib.pyplot as plt
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        >>> fig.minimize('all')    # Minimizes all unhidden figures
        >>> fig.minimize()         # same as minimize('all')
        >>> fig.minimize(plt.gcf().number)  # Minimizes the current figure
        >>> fig.minimize(3)        # Minimizes figure 3
        >>> fig.minimize([2, 4])   # Minimizes figures 2 and 4

        or alternatively
            fig.minimize(2, 4)
        >>> fig.close()

        See also
        --------
        fig.cycle,
        fig.keep,
        fig.restore

        """
        self._show_figs(
            self._parse_figure_numbers(*figure_numbers), win32con.SW_SHOWMINIMIZED
        )

    def maximize(
        self,
        *figure_numbers: FigureArg,
    ) -> None:
        """
        Maximize figure windows.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to maximize (default 'all').

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(5):
        ...     f = plt.figure(ix)
        >>> fig.maximize('all')   # Maximizes all unhidden figures
        >>> fig.maximize()        # same as maximize('all')
        >>> fig.maximize(plt.gcf().number)   # Maximizes the current figure
        >>> fig.maximize(3)       # Maximizes figure 3
        >>> fig.maximize([2, 4])  # Maximizes figures 2 and 4

        or alternatively
            fig.maximize(2, 4)
        >>> fig.close()

        See also
        --------
        fig.cycle,
        fig.keep,
        fig.restore

        """
        self._show_figs(
            self._parse_figure_numbers(*figure_numbers), win32con.SW_SHOWMAXIMIZED
        )

    # ------------------------------------------------------------------
    # Layout Manipulators
    # ------------------------------------------------------------------

    def set_size(
        self,
        *figure_numbers: FigureArg,
        width: int | None = None,
        height: int | None = None,
        position: Position | None = None,
    ) -> None:
        """
        Set the size of the specified figure windows.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to pile (default 'all').
        width : int, optional
            Desired window width. Defaults to a fraction of screen width.
        height : int, optional
            Desired window height. Defaults to a fraction of screen height.
        position : (int, int), optional
            If given, sets the upper-left corner; otherwise uses current position.

        Description
        -------------
        Set size sets the size of all open figure windows. SET_SIZE(FIGS)
        can be used to specify which figures that should be resized.
        Figures are not sorted when specified.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(7):
        ...     f = plt.figure(ix)
        >>> fig.set_size(7, width=150, height=100)
        >>> fig.set_size(list(range(1,4)), 5,width=250, height=170)
        >>> fig.close()

        See also
        --------
        fig.cycle, fig.keep, fig.maximize, fig.restore,
                fig.stack, fig.tile

        """
        handles = self.find_figure_handles(*figure_numbers)
        if not handles:
            return
        sw, sh = self._screen_size_from_handles(handles)
        if width is None:
            width = int(sw / 2.5)
        if height is None:
            height = int(sh / 2)

        for h in handles:
            if position is None:
                x, y, _, _ = self.get_window_position_and_size(h)
            else:
                x, y = position
            _move_window(h, x, y, width, height, True)
            _bring_to_top(h)

    def pile(
        self,
        *figure_numbers: FigureArg,
        width: int | None = None,
        height: int | None = None,
        position: Position | None = None,
    ) -> None:
        """
        Place figure windows directly on top of each other.

        Parameters
        ----------
        figure_numbers : list of integers or string
            specifying which figures to pile (default 'all').
        width : int, optional
            Width of piled windows.
        height : int, optional
            Height of piled windows.
        position : (int, int), optional
            Upper-left corner for the pile.

        Description
        -------------
        PILE piles all open figure windows on top of each other
        with complete overlap. PILE(FIGS) can be used to specify which
        figures that should be piled. Figures are not sorted when specified.

        Notes
        -----
        All windows share the same size and position and are brought to
        the top of the Z-order in sequence.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(7):
        ...     f = plt.figure(ix)
        >>> fig.pile()                  # pile all open figures
        >>> fig.pile(list(range(1,4)), 5, 7)  # pile figure 1,2,3,5 and 7
        >>> fig.close()

        See also
        --------
        fig.cycle, fig.keep, fig.maximize, fig.restore,
                fig.stack, fig.tile

        """

        handles = self.find_figure_handles(*figure_numbers)
        if not handles:
            return
        sw, sh = self._screen_size_from_handles(handles)
        if position is None:
            position = (int(sw / 5), int(sh / 4))
        if width is None:
            width = int(sw / 2.5)
        if height is None:
            height = int(sh / 2)
        x, y = position
        for h in handles:
            _move_window(h, x, y, width, height, True)
            _bring_to_top(h)

    def stack(
        self,
        *figure_numbers: FigureArg,
        figs_per_stack: int | None = None,
    ) -> None:
        """
        Stack figure windows vertically with slight offsets.

        Parameters
        ----------
        *figure_numbers : str, int or sequence of int
            Figures to stack. (default 'all').
        figs_per_stack : int, optional
            Number of figures per stack when multiple monitors or tall
            screens are used. (default depends on screenheight)

        Description
        -----------
        STACK stacks all open figure windows on top of each other
        with maximum overlap. STACK(FIGS) can be used to specify which
        figures that should be stacked. Figures are not sorted when specified.

        Notes
        -----
        Each window is moved by fixed x/y offsets relative to the previous
        one to create a "staircase" appearance.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(7):
        ...     f = plt.figure(ix)
        >>> fig.stack()                # stack all open figures
        >>> fig.stack(list(range(1,4)), 5, 7)  # stack figure 1,2,3,5 and 7
        >>> fig.close()

        See also
        --------
        fig.cycle, fig.keep, fig.maximize, fig.restore,
                fig.pile, fig.tile

        """

        handles = self.find_figure_handles(*figure_numbers)
        if not handles:
            return
        sx, sy, _sw, sh = self.get_screen_position_and_size(handles)
        y_step = 25
        x_step = border = 5
        if figs_per_stack is None:
            figs_per_stack = int(_np.fix(0.7 * (sh - border) / y_step))

        for iy, h in enumerate(handles):
            _x, _y, w, hgt = self.get_window_position_and_size(h)
            ix = iy % max(figs_per_stack, 1)
            new_y = int(sy + ix * y_step + border)
            new_x = int(sx + ix * x_step + border)
            _move_window(h, new_x, new_y, w, hgt, True)
            _bring_to_top(h)

    def tile(self, *figure_numbers: FigureArg, pairs: int | None = None) -> None:
        """
        Tile figure windows into a grid without overlap.

        Parameters
        ----------
        *figure_numbers : str, int or sequence of int
            Figures to tile.  (default 'all')
        pairs : int, optional
            Maximum number of figures per tile layer.

        Description
        -----------
        TILE places all open figure windows around on the screen with no
        overlap. TILE(FIGS) can be used to specify which figures that
        should be tiled. Figures are not sorted when specified.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(7):
        ...     f = plt.figure(ix)
        >>> fig.tile()             # tile all open figures
        >>> fig.tile(list(range(1,4)), 5, 7)    # tile figure 1,2,3,5 and 7
        >>> fig.tile(list(range(1,11)), pairs=2) # tile figure 1 to 10 two at a time
        >>> fig.tile(list(range(1,11)), pairs=3) # tile figure 1 to 10 three at a time
        >>> fig.close()

        See also
        --------
        fig.cycle, fig.keep, fig.maximize, fig.minimize
        fig.restore, fig.pile, fig.stack

        """
        handles = self.find_figure_handles(*figure_numbers)
        nfigs = len(handles)
        if nfigs == 0:
            return
        n_per_tile = nfigs if pairs is None else pairs
        nlayers = int(_np.ceil(nfigs / float(n_per_tile)))
        nh = int(max(2, _np.ceil(_np.sqrt(n_per_tile))))
        nv = int(max(2, _np.ceil(n_per_tile / float(nh))))

        sx, sy, sw, sh = self.get_screen_position_and_size(handles)
        hspc, topspc, medspc, botspc = 10, 20, 10, 20

        fig_w = int(_np.round((sw - (nh + 1) * hspc) / float(nh)))
        fig_h = int(_np.round((sh - (topspc + botspc) - (nv - 1) * medspc) / float(nv)))

        idx = 0
        for _layer in range(nlayers):
            for row in range(nv):
                top = int(sy + topspc + row * (fig_h + medspc))
                for col in range(nh):
                    if row * nh + col < n_per_tile and idx < nfigs:
                        left = int(sx + (col + 1) * hspc + col * fig_w)
                        h = handles[idx]
                        _move_window(h, left, top, fig_w, fig_h, True)
                        _bring_to_top(h)
                        idx += 1

    # ------------------------------------------------------------------
    # Cycle (GUI or console)
    # ------------------------------------------------------------------

    def cycle(
        self,
        *figure_numbers: FigureArg,
        pairs: int = 1,
        maximize: bool = False,
        interval: Interval = "user_defined",
    ) -> None:
        """
        Cycle through figure windows.

        Parameters
        ----------
        *figure_numbers : int or sequence of int
            Figures to cycle through. Defaults to “all figures”.
        pairs : int, optional
            Number of figures to show at a time.
        maximize : bool, optional
            If True, show windows maximized.
        interval : float or 'user_defined', optional
            If numeric, auto-advance after this many seconds; otherwise
            wait for user input.

        Description
        -----------
        CYCLE brings up all open figure in ascending order and pauses after
        each figure. Press escape to quit cycling, backspace to display previous
        figure(s) and press any other key to display next figure(s)
        When done, the figures are sorted in ascending order.

        CYCLE(maximize=True) does the same thing, except figures are maximized.
        CYCLE(pairs=2)   cycle through all figures in pairs of 2.

        Notes
        -----
        In prefer_wx mode, uses a wx-based dialog if wxPython is available.
        If wx is missing or prefer_wx is False, uses a console UI.

        Examples
        --------
        >>> import matplotlib.pyplot as plt
        >>> import fig
        >>> for ix in range(4):
        ...     f = plt.figure(ix)

        fig.cycle(np.arange(3), interval=1)  # Cycle through figure 0 to 2

        # Cycle through figure 0 to 2 with figures maximized
        fig.cycle(np.arange(3), maximize=True, interval=1)
        fig.cycle(interval=1)            # Cycle through all figures one at a time
        fig.tile(pairs=2, interval=1)
        fig.cycle(pairs=2, interval=2)   # Cycle through all figures two at a time

        fig.cycle(pairs=2)      # Manually cycle through all figures two at a time
        >>> fig.close()

        See also
        --------
            fig.keep, fig.maximize, fig.restore, fig.pile,
                fig.stack, fig.tile

        """
        handles = self.find_figure_handles(*figure_numbers)
        if not handles:
            return

        cmd = win32con.SW_SHOWMAXIMIZED if maximize else win32con.SW_SHOWNORMAL

        if self.prefer_wx and wx is not None:
            self._cycle_wx(handles, cmd, pairs, interval)
        else:
            self._cycle_console(handles, cmd, pairs, interval)

        # Restore style after cycling
        for h in handles:
            _show_window(h, win32con.SW_SHOWNORMAL)

    # ------------------------------------------------------------------
    # Cycle Implementations
    # ------------------------------------------------------------------

    def _cycle_console(
        self,
        handles: Sequence[Handle],
        command: int,
        pairs: int,
        interval: Interval,
    ) -> None:
        """
        Console-based cycling UI used when wx is unavailable or disabled.

        Parameters
        ----------
        handles : sequence of int
            Windows to cycle through.
        command : int
            Win32 ShowWindow command.
        pairs : int
            Number of windows shown at a time.
        interval : float or 'user_defined'
            Wait time between windows (float) or wait for input.
        """

        def _next_index(i: int) -> int:
            if isinstance(interval, (int, float)):
                time.sleep(max(0.0, float(interval)))
                return i + pairs

            try:
                s = input("[Enter=forward, b=back, q=quit] ").strip().lower()
            except EOFError:
                s = ""

            if s == "b":
                return i - pairs
            if s == "q":
                return -1
            return i + pairs

        i, n = 0, len(handles)
        while 0 <= i < n:
            for h in handles[i : i + pairs]:
                _show_window(h, command)
                _redraw_window_now(h)
            i = _next_index(i)

    def _cycle_wx(
        self,
        handles: Sequence[Handle],
        command: int,
        pairs: int,
        interval: Interval,
    ) -> None:
        """
        wxPython-based cycling UI (prefer_wx mode).

        Parameters
        ----------
        handles : sequence of int
            Windows to cycle through.
        command : int
            Win32 ShowWindow command.
        pairs : int
            Number of windows shown at a time.
        interval : float or 'user_defined'
            Timer interval or manual stepping trigger.

        Notes
        -----
        Mirrors original wx behavior as closely as possible.
        """
        if wx is None:  # fallback
            self._cycle_console(handles, command, pairs, interval)
            return

        class CycleDialog(wx.Dialog):
            def __init__(self, parent = None, interval = None, title="Cycle dialog"):
                super().__init__(parent, title=title, size=(260, 130))
                if isinstance(interval, (int, float)):
                    self.interval_ms = int(interval * 1000)
                else:
                    self.interval_ms = 30
                self.timer = wx.Timer(self)
                self.Bind(wx.EVT_TIMER, self.on_forward, self.timer)

                vbox = wx.BoxSizer(wx.VERTICAL)
                vbox.Add(self._msg(), 0, wx.ALIGN_CENTER | wx.TOP, 20)
                vbox.Add(self._buttons(), 1, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 10)
                self.SetSizer(vbox)

            def _msg(self):
                msg = (
                    "Press Back or Forward to cycle through figures.\n"
                    "Press Cancel to exit."
                )
                return wx.StaticText(self, label=msg, size=(240, 40))

            def _buttons(self):
                hbox = wx.BoxSizer(wx.HORIZONTAL)
                buttons = ["Forward", "Back", "Cancel"]
                callbacks = [self.on_forward, self.on_backward, self.on_cancel]
                for label, cb in zip(buttons, callbacks):
                    b = wx.Button(self, -1, label, size=(70, 30))
                    self.Bind(wx.EVT_BUTTON, cb, b)
                    hbox.Add(b, 1, wx.ALIGN_CENTER)
                return hbox

            def ShowModal(self, *a, **k):
                self.timer.Start(self.interval_ms, oneShot=True)
                return super().ShowModal(*a, **k)

            def on_forward(self, evt):
                self.EndModal(wx.ID_FORWARD)

            def on_backward(self, evt):
                self.EndModal(wx.ID_BACKWARD)

            def on_cancel(self, evt):
                self.EndModal(wx.ID_CANCEL)

        app = wx.GetApp()
        if not app:
            app = wx.App(redirect=False)
            frame = wx.Frame(None)
            app.SetTopWindow(frame)

        dlg = CycleDialog(interval=interval)
        try:
            i, n = 0, len(handles)
            while 0 <= i < n:
                for h in handles[i : i + pairs]:
                    _show_window(h, command)
                    _redraw_window_now(h)

                r = dlg.ShowModal()
                if r == wx.ID_FORWARD:
                    i += pairs
                elif r == wx.ID_BACKWARD:
                    i -= pairs
                else:
                    break
        finally:
            dlg.Destroy()

    # ------------------------------------------------------------------
    # Internal Helper
    # ------------------------------------------------------------------

    def _show_figs(
        self,
        nums: Sequence[int],
        command: int,
    ) -> None:
        """Internal helper to apply Win32 ShowWindow command to given figures."""

        wanted = set(nums)

        for h, title in _enum_windows():
            m = self._figure_re.match(title)
            if m and int(m.group(1)) in wanted:
                _bring_to_top(h)
                _show_window(h, command)

    def _screen_size_from_handles(
        self,
        handles: Sequence[Handle],
    ) -> tuple[int, int]:
        """Return (screen_width, screen_height) helper."""
        _, _, w, h = self.get_screen_position_and_size(handles)
        return w, h


# ======================================================================
# Global Instance and Procedural API
# ======================================================================

_wm = WindowManager(prefer_wx=_DEFAULT_USE_WX)



def set_prefer_wx(enable: bool) -> None:
    """
    Enable or disable wx-based figure cycling.

    Parameters
    ----------
    enable : bool
        If True, use the wxPython cycling dialog when wx is available.
        If False, use the console-based cycling interface.
    """
    global _wm
    _wm = WindowManager(prefer_wx=bool(enable))



def _delegate(method_name: str) -> Callable[..., Any]:
    method = getattr(WindowManager, method_name)

    @wraps(method)
    def wrapper(*args, **kwargs):
        return getattr(_wm, method_name)(*args, **kwargs)

    return wrapper


# ---------------- Procedural Wrappers (Preserve Original API) ---------
close = _delegate("close")
keep = _delegate("keep")
hide = _delegate("hide")
restore = _delegate("restore")
minimize = _delegate("minimize")
maximize = _delegate("maximize")
pile = _delegate("pile")
stack = _delegate("stack")
tile = _delegate("tile")
cascade = _delegate("cascade")
center = _delegate("center")
snap_left = _delegate("snap_left")
snap_right = _delegate("snap_right")
snap_top = _delegate("snap_top")
snap_bottom = _delegate("snap_bottom")
cycle = _delegate("cycle")

find_figure_handles = _delegate("find_figure_handles")
find_all_figure_numbers = _delegate("find_all_figure_numbers")
get_window_position_and_size = _delegate("get_window_position_and_size")
get_screen_position_and_size = _delegate("get_screen_position_and_size")
set_size = _delegate("set_size")


# ======================================================================
# Stand-alone test helper
# ======================================================================

if __name__ == "__main__":
    # print("Mode:", "wx" if _wm.prefer_wx else "console")
    # print("Figures:", find_all_figure_numbers())
    from utilities.testing import test_docstrings
    import matplotlib

    matplotlib.interactive(True)
    test_docstrings(__file__)
