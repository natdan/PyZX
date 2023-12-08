#!/usr/bin/env python3

"""
ZX Spectrum Emulator
Vadim Kataev
www.technopedia.org
"""

import sys

from z80.memory import Memory
from z80.z80 import Z80
from spectrum.keyboard import Keyboard
from spectrum.spectrum_bus_access import ZXSpectrum48ClockAndBusAccess
from spectrum.spectrum_ports import SpectrumPorts
from spectrum.video import TSTATES_PER_INTERRUPT, Video


ROMFILE = '48.rom'

# As per https://worldofspectrum.org/faq/reference/48kreference.htm


class Spectrum:
    def __init__(self):
        self.keyboard = Keyboard()
        self.ports = SpectrumPorts(self.keyboard)
        self.memory = Memory()

        self.video = Video(self.memory, self.ports, ratio=3)

        self.bus_access = ZXSpectrum48ClockAndBusAccess(
            self.memory,
            self.ports,
            self.video.update_next_screen_word)

        self.z80 = Z80(self.bus_access, self.memory)

        self.video_update_time = 0

        self.video.init()

    def load_rom(self, romfilename):
        with open(romfilename, "rb") as rom:
            rom.readinto(self.memory.mem)

        print(f"Loaded ROM: {romfilename}")

    def init(self):
        self.load_rom(ROMFILE)
        self.ports.out_port(254, 0xff)  # white border on startup
        self.z80.reset()
        self.bus_access.reset()

        sys.setswitchinterval(255)  # we don't use threads, kind of speed up

    def process_video_and_keyboard(self):
        self.ports.keyboard.do_keys()
        self.video.update_zx_screen()
        self.video.update(self.bus_access.frames, self.bus_access.tstates)

    def run(self):
        try:
            while True:
                self.bus_access.next_screen_byte_index = 0
                self.video.start_screen()

                self.z80.execute(TSTATES_PER_INTERRUPT)
                self.bus_access.end_frame(TSTATES_PER_INTERRUPT)
                self.process_video_and_keyboard()
        except KeyboardInterrupt:
            return
