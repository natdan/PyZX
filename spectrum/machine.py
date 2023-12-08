#!/usr/bin/env python3

"""
ZX Spectrum Emulator
Vadim Kataev
www.technopedia.org
"""
import os.path
from typing import Callable

import sys

from z80.memory import Memory
from z80.z80 import Z80
from spectrum.keyboard import Keyboard
from spectrum.spectrum_bus_access import ZXSpectrum48ClockAndBusAccess
from spectrum.spectrum_ports import SpectrumPorts
from spectrum.video import TSTATES_PER_INTERRUPT, Video


ROMFILE = "zxspectrum48k.rom"


class Spectrum:
    def __init__(self):
        self.keyboard = Keyboard()
        self.ports = SpectrumPorts(self.keyboard)
        self.memory = Memory()

        self.video = Video(self.memory, self.ports)

        self.bus_access = ZXSpectrum48ClockAndBusAccess(
            self.memory,
            self.ports,
            self.video.update_next_screen_word)

        self.z80 = Z80(self.bus_access, self.memory)

        self.video_update_time = 0

        self.video.init()

    def load_rom(self, romfilename):
        with open(os.path.join(os.path.dirname(__file__), romfilename), "rb") as rom:
            rom.readinto(self.memory.mem)

        print(f"Loaded ROM: {romfilename}")

    def init(self):
        self.load_rom(ROMFILE)
        self.ports.out_port(254, 0xff)  # white border on startup
        self.z80.reset()
        self.bus_access.reset()

        sys.setswitchinterval(255)  # we don't use threads, kind of speed up

    def end_frame(self) -> None:
        self.bus_access.end_frame(TSTATES_PER_INTERRUPT)
        self.video.finish_screen()
        self.video.update()
        self.video.start_screen()

    def execute(self, tstate_limit: int) -> None:
        self.z80.execute(tstate_limit)
