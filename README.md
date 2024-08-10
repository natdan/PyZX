# PyZX - Python ZX Spectrum Emulator
PyZX is a ZX Spectrum emulator written entirely in Python. It is based on Vadim Kataev's PyZX Python Spectrum Emulator and is licensed under the GPL-2 license.

## Requirements
- Python 3.x (available at [python.org](https://www.python.org))
- PyGame 1.7+ (available at [pygame.org](https://www.pygame.org))

## Running the Emulator
To run the emulator, use the following command:
```bash
python3 spectrum.py
```

Optionally, you can use the `-OO` optimization flag for potentially better performance:
```bash
python3 -OO spectrum.py
```

## Controls
- **Ctrl + Alt**: Switch to special mode
- **Alt + AnyKey**: Symbol shift
- **Ctrl (in normal mode) + AnyKey**: Big/small characters
- **Ctrl (in special mode) + AnyKey**: Symbol shift 2

## Acknowledgements
Thanks to Jasper ([spectrum.lovely.net](http://www.spectrum.lovely.net/)) for the excellent Java emulator of the ZX Spectrum. A significant portion of the code was automatically translated from Java to Python, and further optimization and rewriting are needed to improve emulation speed.

## TODO
- Implement a more Pythonic approach for the core (Z80 CPU)
- Add threading for parallel processing (video and possibly keyboard)
- Support for TAP/TZX files

## Authors
- Vadim Kataev (initial version)
- Stanislav Yudin (initial conversion to Python 3)
- Vladimir Berezenko
