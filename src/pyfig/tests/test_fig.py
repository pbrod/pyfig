import sys
import time
from unittest.mock import patch

import pytest

import matplotlib.pyplot as plt

if sys.platform == "win32":
    from pyfig import fig
    from pyfig.fig import WindowManager


pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only package",
)


def test_parse_single_int() -> None:
    wm = WindowManager()
    assert wm._parse_figure_numbers(5) == [5]


def test_parse_list() -> None:
    wm = WindowManager()
    assert wm._parse_figure_numbers([1, 2, 3]) == [1, 2, 3]


def test_parse_nested_iterables() -> None:
    wm = WindowManager()
    assert wm._parse_figure_numbers(1, (2, 3)) == [1, 2, 3]


def test_parse_all_uses_find_all() -> None:
    wm = WindowManager()
    with patch.object(wm, "find_all_figure_numbers", return_value=[9, 8, 7]):
        assert wm._parse_figure_numbers("all") == [9, 8, 7]


def test_parse_invalid_type() -> None:
    wm = WindowManager()
    with pytest.raises(TypeError):
        wm._parse_figure_numbers(object())


def test_safe_call_swallows_win32_errors() -> None:
    def boom():
        raise fig.win32gui.error("err")

    assert fig._safe_call(boom) is None


def test_keep_closes_complement() -> None:
    wm = WindowManager()
    with (
        patch.object(wm, "find_all_figure_numbers", return_value=[1, 2, 3, 4]),
        patch.object(wm, "close") as mock_close,
    ):
        wm.keep(1, 3)
        mock_close.assert_called_once_with(2, 4)


# @pytest.mark.windows_only
class TestFigIntegration:
    def wait_for_figs(
        self,
        expected_count: int,
        timeout: float = 5.0,
    ) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if len(fig.find_all_figure_numbers()) == expected_count:
                return True
            time.sleep(0.05)
        return False

    def setup_method(self) -> None:
        plt.close("all")
        for i in range(10):
            plt.figure(i)
        plt.draw()
        plt.pause(0.1)
        assert self.wait_for_figs(10)

    def teardown_method(self) -> None:
        plt.close("all")
        self.wait_for_figs(0)

    def test_close_single(self) -> None:
        fig.close(0)
        assert self.wait_for_figs(9)
        assert 0 not in fig.find_all_figure_numbers()

    def test_keep_subset(self):
        fig.keep(1, 2, 3, 5, 9)
        final = fig.find_all_figure_numbers()
        assert sorted(final) == [1, 2, 3, 5, 9]

    def test_close_all(self) -> None:
        fig.close("all")
        assert self.wait_for_figs(0)

    def test_pile(self) -> None:
        fig.pile([1, 2], width=150, height=100)
        handles = fig.find_figure_handles(1, 2)
        positions = [fig.get_window_position_and_size(h) for h in handles]
        assert positions[0][2:] == (150, 100)
        assert positions[0] == positions[1]

    def test_stack(self) -> None:
        figs = list(range(5))
        fig.stack(figs)
        handles = fig.find_figure_handles(figs)
        positions = [fig.get_window_position_and_size(h)[0:2] for h in handles]
        diffs = [
            (
                positions[i + 1][0] - positions[i][0],
                positions[i + 1][1] - positions[i][1],
            )
            for i in range(len(positions) - 1)
        ]
        assert len(set(diffs)) == 1

    def test_minimize(self) -> None:
        fig.minimize(1)
        pos = fig.get_window_position_and_size(fig.find_figure_handles(1)[0])
        assert pos[0] <= -32000 or pos[1] <= -32000  # Windows minimized location
