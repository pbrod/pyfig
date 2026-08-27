# pyfig

Interactive figure and window management for Windows.

`pyfig` is a Windows-only Python package for interactively arranging and managing figure windows created by Matplotlib, Mayavi/TVTK, and Chaco.

It provides simple functions for:

- Tiling, stacking, piling, and cascading windows
- Minimizing, maximizing, restoring, and hiding figures
- Snapping windows to screen regions
- Cycling through figures
- Closing or keeping selected figures
- Querying figure positions and screen geometry

The package uses the Win32 API and works directly with figure windows after they have been created.

---

## Gallery

The examples below use Matplotlib figures, but pyfig can also manipulate
Mayavi/TVTK and Chaco figure windows.

### Tile all open figures

Arrange all open figures in a non-overlapping grid:

```python
from pyfig import fig

fig.tile()
```

![Tile layout](https://raw.githubusercontent.com/pbrod/pyfig/main/docs/images/tile.png)

### Stack all open figures with partial overlap

Arrange figures with a staircase-style overlap:

```python
from pyfig import fig

fig.stack()
```

![Stack layout](https://raw.githubusercontent.com/pbrod/pyfig/main/docs/images/stack.png)


### Snap a figure to the right side of the screen

Snap figure number four to the right half of the screen.

```python
fig.snap_right(4)
```

![Snap-right layout](https://raw.githubusercontent.com/pbrod/pyfig/main/docs/images/snap_right.png)

---

## Features

The screenshots above demonstrate only a subset of the functionality available in pyfig.

### Window management

```python
fig.maximize()
fig.minimize()
fig.restore()
fig.hide()
```

### Layout management

```python
fig.tile()
fig.stack()
fig.pile()
fig.cascade()
```

### Screen snapping

```python
fig.snap_left()
fig.snap_right()
fig.snap_top()
fig.snap_bottom()
```

### Figure selection

```python
fig.close(1, 2)
fig.keep(3)
```

### Interactive cycling

```python
fig.cycle()
fig.cycle(pairs=2)
fig.cycle(interval=1.0)
```

---

## Requirements

- Windows
- Python 3.10+
- pywin32

---

## Installation

### Matplotlib support

```bash
pip install pyfig[plot]
```

### Core package

```bash
pip install pyfig
```

### wxPython support

```bash
pip install pyfig[wx]
```

### Everything

```bash
pip install pyfig[plot,wx]
```

---

## Quick Check

After installation, verify that pyfig is working:

```python
import pyfig

pyfig.test()
```

---

## Quick Start

Create some figures:

```python
import matplotlib.pyplot as plt

for i in range(1, 5):
    plt.figure(i)
```

Arrange them:

```python
from pyfig import fig

fig.tile()
```

Stack them:

```python
fig.stack()
```

Pile them:

```python
fig.pile()
```

Maximize a figure:

```python
fig.maximize(4)
```

Close all figures:

```python
fig.close()
```

---

## Examples

### Tile all open figures

```python
import matplotlib.pyplot as plt
from pyfig import fig

for i in range(1, 5):
    plt.figure(i)

fig.tile()
```

### Keep only selected figures

```python
fig.keep(1, 3)
```

### Snap a figure to the right side of the screen

```python
fig.snap_right(4)
```

### Center all figures

```python
fig.center()
```

### Cycle through open figures

```python
fig.cycle(interval=1.0)
```

### Cycle through figures in pairs

```python
fig.cycle(pairs=2)
```

---

## Public API

All functionality is available through the `pyfig.fig` module:

### Window operations

```python
close()
hide()
restore()
minimize()
maximize()
keep()
cycle()
```

### Layout operations

```python
tile()
stack()
pile()
cascade()
center()
set_size()
```

### Screen snapping

```python
snap_left()
snap_right()
snap_top()
snap_bottom()
```

### Information functions

```python
find_all_figure_numbers()
find_figure_handles()

get_window_position_and_size()
get_screen_position_and_size()
```

### Configuration

```python
set_prefer_wx()
```

---

## wxPython Support

If wxPython is installed, pyfig can provide a GUI dialog for figure cycling.

Enable it by setting the environment variable:

```bash
set FIG_USE_WX=1
```

or programmatically:

```python
from pyfig import fig

fig.set_prefer_wx(True)
```

Without wxPython, pyfig automatically falls back to a console-based interface.

---

## Testing

pyfig includes a convenience function for running its test suite.

Run all tests:

```python
import pyfig

pyfig.test()
```

Run with additional pytest options:

```python
import pyfig

pyfig.test("-v")
```

Show available pytest options:

```python
import pyfig

pyfig.test("--help")
```

For development, tests may also be executed directly using PDM:

```bash
pdm run tests
```

or:

```bash
pdm all-tests
```

---

## License

BSD License.

See the `LICENSE` file for details.