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

from bus_access import BusAccess
from clock import Clock
# import load

from keyboard import Keyboard
from ports import Ports
from memory import Memory
from video import Video, SCREEN_HEIGHT, TSTATES_PER_INTERRUPT, TSTATES_LEFT_BORDER, TSTATES_FIRST_LINE, FIRST_PIXEL_LINE, TSTATES_PER_LINE, TSTATES_PIXELS, TSTATES_RIGHT_BORDER, TSTATES_RETRACE, \
    NUMBER_OF_LINES
from z80 import Z80

from load import Load


ROMFILE = '48.rom'
SNADIR = 'games/'

# As per https://worldofspectrum.org/faq/reference/48kreference.htm

INTERRUPT_LENGTH = 24


class ZXSpectrum48BusAccess(BusAccess):
    def __init__(self,
                 clock: Clock,
                 memory: Memory,
                 ports: Ports) -> None:
        super().__init__(clock, memory, ports)

    def fetch_opcode(self, address: int) -> int:
        t = self.memory.peekb(address)
        self.clock.tstates += 4
        return t

    def peekb(self, address: int) -> int:
        self.clock.tstates += 3
        return self.memory.peekb(address)

    def peeksb(self, address: int) -> int:
        self.clock.tstates += 3
        return self.memory.peeksb(address)

    def pokeb(self, address: int, value: int) -> None:
        self.clock.tstates += 3
        self.memory.pokeb(address, value & 0xFF)

    def peekw(self, address: int) -> int:
        lsb = self.peekb(address)
        msb = self.peekb((address + 1) & 0xFFFF)

        return (msb << 8) + lsb

    def pokew(self, address: int, value: int) -> None:
        self.memory.pokeb(address, value & 0xff)
        self.memory.pokeb(address + 1, (value >> 8))

    def address_on_bus(self, address: int, tstates: int) -> None:
        self.clock.tstates += tstates

    def interrupt_handling_time(self, tstates: int) -> None:
        self.clock.tstates += tstates

    def in_port(self, port: int) -> int:
        return self.ports.in_port(port)

    def out_port(self, port: int, value: int):
        self.ports.out_port(port, value)

    def is_active_INT(self) -> bool:
        current = self.clock.tstates
        if current >= TSTATES_PER_INTERRUPT:
            current -= TSTATES_PER_INTERRUPT

        return 0 < current < INTERRUPT_LENGTH


class Spectrum():
    def __init__(self):
        self.clock = Clock()

        self.keyboard = Keyboard()
        self.ports = Ports(self.keyboard)
        self.memory = Memory()

        self.video = Video(self.clock, self.memory, self.ports, ratio=2)

        self.bus_access = ZXSpectrum48BusAccess(self.clock, self.memory, self.ports)
        self.z80 = Z80(
            self.clock,
            self.bus_access,
            self.memory,
            self.clock_cycle_test)
        self.video_update_time = 0
        # self.clock.tstates -= self.tstates_per_interrupt
        self.clock.tstates -= TSTATES_LEFT_BORDER

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
        self.ports.out_port(254, 0xff)  # white border on startup
        self.z80.reset()
        self.clock.reset()

        sys.setswitchinterval(255)  # we don't use threads, kind of speed up

    def process_video_and_keyboard(self):
        self.ports.keyboard.do_keys()
        # self.video.fill_screen_map()
        self.video.update_zx_screen()
        self.video.update()

    def clock_cycle_test(self) -> bool:
        if self.clock.tstates >= 0:
            return self.tstates_state()

            # set for next vertical blanking interrupt
            # self.clock.tstates -= TSTATS_PER_INTERRUPT
            #
            # self.process_video_and_keyboard()
            #
            # # Handle interrupt in the processor add clock cycles for handling of the interrupt
            # self.clock.tstates += self.z80.interruptCPU()
            # return True
        return False

    def tstates_interrupt(self) -> bool:
        # set for next vertical blanking interrupt
        self.clock.tstates -= TSTATES_FIRST_LINE
        self.tstates_total = TSTATES_FIRST_LINE
        self.tstates_state = self.tstates_first_border_lines
        self.tstates_current_line = 0

        self.process_video_and_keyboard()
        self.clock.end_frame(TSTATES_PER_INTERRUPT)

        # Handle interrupt in the processor add clock cycles for handling of the interrupt
        self.clock.tstates += self.z80.interruptCPU()
        return True

    def tstates_first_border_lines(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < FIRST_PIXEL_LINE:
            self.clock.tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
        else:
            self.clock.tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_after_left_border
        return False

    def tstates_after_left_border(self) -> bool:
        self.clock.tstates -= TSTATES_PIXELS
        self.tstates_total += TSTATES_PIXELS
        self.tstates_state = self.tstates_after_pixels
        return False

    def tstates_after_pixels(self) -> bool:
        self.video.fill_screen_map_line(self.tstates_current_line - FIRST_PIXEL_LINE)

        self.clock.tstates -= TSTATES_RIGHT_BORDER
        self.tstates_total += TSTATES_RIGHT_BORDER
        self.tstates_state = self.tstates_after_right_border

        return False

    def tstates_after_right_border(self) -> bool:
        self.clock.tstates -= TSTATES_RETRACE
        self.tstates_total += TSTATES_RETRACE
        self.tstates_state = self.tstates_after_retrace
        return False

    def tstates_after_retrace(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < FIRST_PIXEL_LINE + SCREEN_HEIGHT:
            self.clock.tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_after_left_border
        else:
            self.clock.tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
            self.tstates_state = self.tstates_last_border_lines
        return False

    def tstates_last_border_lines(self) -> bool:
        self.tstates_current_line += 1
        if self.tstates_current_line < NUMBER_OF_LINES:
            self.clock.tstates -= TSTATES_PER_LINE
            self.tstates_total += TSTATES_PER_LINE
        else:
            self.clock.tstates -= TSTATES_LEFT_BORDER
            self.tstates_total += TSTATES_LEFT_BORDER
            self.tstates_state = self.tstates_interrupt
        return False

    def run(self):
        """ Start the execution """
        try:
            while True:
                self.z80.execute(TSTATES_PER_INTERRUPT)
                self.clock.end_frame(TSTATES_PER_INTERRUPT)
                self.video.fill_screen_map()
                self.process_video_and_keyboard()
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    spectrum = Spectrum()
    spectrum.init()
    load = Load(spectrum.z80, spectrum.ports)
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
