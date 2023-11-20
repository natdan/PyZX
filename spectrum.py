#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ZX Spectrum Emulator
Vadim Kataev
www.technopedia.org

ver.0.1 2005
ver.0.2 June 2008
Python 3 conversion + modifications by CityAceE 2018
Full z80 core rewrite + optimizations + improvements Q-Master 2019
Simple fixes Bedazzle 2020
"""

import sys

# import load

from keyboard import Keyboard
from ports import Ports
from memory import Memory
from video import Video, SCREEN_HEIGHT
from z80 import Z80

from load import Load

ROMFILE = '48.rom'
SNADIR = 'games/'

# As per https://worldofspectrum.org/faq/reference/48kreference.htm
TSTATS_PER_INTERRUPT = 69888
TSTATES_PER_LINE = 224
TSTATES_LEFT_BORDER = 24
TSTATES_RIGHT_BORDER = 24
TSTATES_PIXELS = 128
TSTATES_RETRACE = 48
TSTATES_FIRST_LINE = TSTATES_PER_LINE - TSTATES_LEFT_BORDER
TSTATES_LAST_LINE = TSTATES_RIGHT_BORDER
NUMBER_OF_LINES = 312
FIRST_PIXEL_LINE = 64


class Spectrum:
    def __init__(self):
        self.keyboard = Keyboard()
        self.ports = Ports(self.keyboard)
        self.memory = Memory()
        self.video = Video(self.memory, self.ports, ratio=2)
        self.z80 = Z80(self.memory, self.ports, self.clock_cycle_test, 3.5)  # Z80.Z80(3.5)  # MhZ
        self.video_update_time = 0
        # self.z80.local_tstates -= self.tstates_per_interrupt
        self.z80.local_tstates -= TSTATES_LEFT_BORDER

        self.video.init()
        self.tstates_state = self.tstates_interrupt
        self.tstates_current_count = 0
        self.tstates_current_line = 0

        self.tstates_total = 0
        # self.interrupt_tstates_count = -TSTATS_PER_INTERRUPT
        # self.line_tstates_count = -TSTATES_PER_LINE

    def load_rom(self, romfilename):
        """ Load given romfile into memory """

        with open(romfilename, 'rb') as rom:
            rom.readinto(self.memory.mem)

        print('Loaded ROM: %s' % romfilename)

    def init(self):
        self.load_rom(ROMFILE)
        self.ports.port_out(254, 0xff)  # white border on startup
        self.z80.reset()

        sys.setswitchinterval(255)  # we don't use threads, kind of speed up

    def process_video_and_keyboard(self):
        self.ports.keyboard.do_keys()
        # self.video.fill_screen_map()
        self.video.update_zx_screen()

        self.video.update()

    def clock_cycle_test(self) -> bool:
        if self.z80.local_tstates >= 0:
            return self.tstates_state()

            # set for next vertical blanking interrupt
            # self.z80.local_tstates -= TSTATS_PER_INTERRUPT
            #
            # self.process_video_and_keyboard()
            #
            # # Handle interrupt in the processor add clock cycles for handling of the interrupt
            # self.z80.local_tstates += self.z80.interruptCPU()
            # return True
        return False

    def tstates_interrupt(self) -> bool:
        # set for next vertical blanking interrupt
        self.z80.local_tstates -= TSTATES_FIRST_LINE
        self.tstates_total = TSTATES_FIRST_LINE
        self.tstates_state = self.tstates_first_border_lines
        self.tstates_current_line = 0

        self.process_video_and_keyboard()

        # Handle interrupt in the processor add clock cycles for handling of the interrupt
        self.z80.local_tstates += self.z80.interruptCPU()
        return True

    def tstates_first_border_lines(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < FIRST_PIXEL_LINE:
            self.z80.local_tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
        else:
            self.z80.local_tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_after_left_border
        return False

    def tstates_after_left_border(self) -> bool:
        self.z80.local_tstates -= TSTATES_PIXELS
        self.tstates_total += TSTATES_PIXELS
        self.tstates_state = self.tstates_after_pixels
        return False

    def tstates_after_pixels(self) -> bool:
        self.video.fill_screen_map_line(self.tstates_current_line - FIRST_PIXEL_LINE)

        self.z80.local_tstates -= TSTATES_RIGHT_BORDER
        self.tstates_total += TSTATES_RIGHT_BORDER
        self.tstates_state = self.tstates_after_right_border

        return False

    def tstates_after_right_border(self) -> bool:
        self.z80.local_tstates -= TSTATES_RETRACE
        self.tstates_total += TSTATES_RETRACE
        self.tstates_state = self.tstates_after_retrace
        return False

    def tstates_after_retrace(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < FIRST_PIXEL_LINE + SCREEN_HEIGHT:
            self.z80.local_tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_after_left_border
        else:
            self.z80.local_tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
            self.tstates_state = self.tstates_last_border_lines
        return False

    def tstates_last_border_lines(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < NUMBER_OF_LINES:
            self.z80.local_tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
        else:
            self.z80.local_tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_interrupt
        return False

    def run(self):
        """ Start the execution """
        try:
            self.z80.execute()
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    spectrum = Spectrum()
    spectrum.init()
    load = Load(spectrum.z80)
    # ok
    # load.load_sna(SNADIR + 'Action Reflex.sna')
    # load.load_sna(SNADIR + 'Ball Breaker 1.sna')
    # load.load_sna(SNADIR + 'Ball Breaker 2.sna')
    # load.load_sna(SNADIR + 'Batty.sna')
    # load.load_sna(SNADIR + 'Bomb Jack.sna')
    # load.load_sna(SNADIR + 'Bruce Lee.sna')
    # load.load_sna(SNADIR + 'Capitan Trueno 1.sna')
    # load.load_sna(SNADIR + 'Cybernoid 1.sna')
    # load.load_sna(SNADIR + 'Cybernoid 2.sna')
    # load.load_sna(SNADIR + 'Cyclone.sna')
    # load.load_sna(SNADIR + 'Eric And The Floaters.sna')
    # load.load_sna(SNADIR + 'Exolon.sna')
    # load.load_sna(SNADIR + 'Freddy Hardest 1.sna')
    # load.load_sna(SNADIR + 'Frost Byte.sna')
    # load.load_sna(SNADIR + 'Head Over Heels.sna')
    # load.load_sna(SNADIR + 'Heavy On The Magick (Rebound).sna')
    # load.load_sna(SNADIR + 'Legions Of Death.sna')
    # load.load_sna(SNADIR + 'Lord Of The Rings (Part 1).sna')
    # load.load_sna(SNADIR + 'Mermaid Madness.sna')
    # load.load_sna(SNADIR + 'Monty On The Run.sna')
    # load.load_sna(SNADIR + 'Movie.sna')
    # load.load_sna(SNADIR + 'Nebulus.sna')
    # load.load_sna(SNADIR + 'Penetrator.sna')
    # load.load_sna(SNADIR + 'Rick Dangerous.sna')
    # load.load_sna(SNADIR + 'Ruff and Reddy.sna')
    # load.load_sna(SNADIR + 'Saboteur 1.sna')
    # load.load_sna(SNADIR + 'Saboteur 2.sna')
    # load.load_sna(SNADIR + 'Scuba Dive.sna')
    # load.load_sna(SNADIR + 'Three Weeks In Paradise.sna')
    # load.load_sna(SNADIR + 'Mask_3_Venom_strikes_back.sna')
    # load.load_sna(SNADIR + 'Yogi Bear.sna')
    # load.load_sna(SNADIR + 'Zynaps.sna')

    # invalid
    # load.load_sna(SNADIR + 'Arkanoid 2.sna')       # vanishing bat
    # load.load_sna(SNADIR + 'Batman.sna')           # blinking sprites
    # load.load_sna(SNADIR + 'Dizzy7.sna')           # vanishing sprite
    # load.load_sna(SNADIR + 'Puzznic.sna')          # no cursor
    # load.load_sna(SNADIR + 'Ramparts.sna')         # tape error
    # load.load_sna(SNADIR + 'Storm Lord.sna')       # blinking sprites

    # load.load_sna(SNADIR + 'bt_city.sna')
    # load.load_sna(SNADIR + 'bt.sna')
    # load.load_sna(SNADIR + 'z80full_with_pause.SNA')

    # load.load_z80(SNADIR + 'Batty.z80')

    # load.load_sna(SNADIR + 'Batman.sna')
    # load.load_sna(SNADIR + "CHUCKEGG 2.SNA")
    load.load_sna(SNADIR + 'nirvana-demo.sna')

    spectrum.run()
