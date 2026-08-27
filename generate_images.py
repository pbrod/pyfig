"""
Generate screenshots for the pyfig README.

Run the script and take screenshots after each layout operation.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from pyfig import fig


def make_figures(num_figures: int = 9) -> None:
    """Create sample figures."""

    x = np.linspace(0, 10, 500)

    for i in range(num_figures):
        plt.figure(i + 1)
        if i == num_figures - 1:
            plt.plot(x, np.sin(x + i), linewidth=3, color="red")
        else:
            plt.plot(x, np.sin(x + i))
        plt.grid(True)

        plt.title(f"Figure {i + 1}")

        plt.tight_layout()


def wait_for_screenshot(title: str) -> None:
    """Pause until the user is ready."""

    print()
    print("=" * 80)
    print(title)
    print("Take a screenshot, then press Enter to continue.")
    print("=" * 80)

    input()


def main() -> None:
    plt.close("all")

    make_figures(num_figures=4)

    plt.show(block=False)
    plt.pause(1.0)

    fig.tile()
    wait_for_screenshot("Tile layout")

    fig.stack()
    wait_for_screenshot("Stack layout")

    fig.snap_right(4)
    wait_for_screenshot("Snap right")

    # fig.cascade()
    # wait_for_screenshot("Cascade layout")

    # fig.pile()
    # wait_for_screenshot("Pile layout")

    # fig.snap_left()
    # wait_for_screenshot("Snap left")

    # fig.snap_top()
    # wait_for_screenshot("Snap top")

    # fig.snap_bottom()
    # wait_for_screenshot("Snap bottom")

    fig.close()


if __name__ == "__main__":
    main()