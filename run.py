#!/usr/bin/env python3

from spectrum.machine import Spectrum
from utils.load import Load
from pygame_emulator import PyGameEmulator


spectrum = Spectrum()
spectrum.init()
load = Load(spectrum.z80, spectrum.ports)

emulator = PyGameEmulator(spectrum, show_fps=True, ratio=3)
emulator.init()


load.load_sna("games/nirvana-demo.sna")

# spectrum.video.fast = True
# spectrum.z80.show_debug_info = True
# spectrum.keyboard.do_key(True, 13, 0)

emulator.run()
