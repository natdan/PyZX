#!/usr/bin/env python3

"""
ZX Spectrum Emulator
Vadim Kataev
www.technopedia.org
"""
from typing import Callable

import sys

from bus_access import ClockAndBusAccess

from keyboard import Keyboard
from ports import Ports
from memory import Memory
from video import Video, SCREEN_HEIGHT, TSTATES_PER_INTERRUPT, TSTATES_LEFT_BORDER, FIRST_PIXEL_LINE, TSTATES_PER_LINE, TSTATES_PIXELS, TSTATES_RIGHT_BORDER, TSTATES_RETRACE, SCREEN_WIDTH
from z80 import Z80

from load import Load


ROMFILE = '48.rom'
SNADIR = 'games/'

# As per https://worldofspectrum.org/faq/reference/48kreference.htm

INTERRUPT_LENGTH = 24


class ZXSpectrum48ClockAndBusAccess(ClockAndBusAccess):
    def __init__(self,
                 memory: Memory,
                 ports: Ports,
                 update_next_screen_byte: Callable) -> None:
        super().__init__(memory, ports)

        self.update_next_screen_word = update_next_screen_byte

        self.delay_tstates = [0] * (TSTATES_PER_INTERRUPT + 200)
        self.screen_byte_tstate = [TSTATES_PER_INTERRUPT * 2] * (1 + SCREEN_HEIGHT * SCREEN_WIDTH // 16)
        self.next_screen_byte_index = 0

        screen_byte_inx = 0

        for i in range(14335, 57247, TSTATES_PER_LINE):
            for n in range(0, 128, 8):
                frame = i + n
                self.screen_byte_tstate[screen_byte_inx] = frame + 2
                screen_byte_inx += 1

                self.delay_tstates[frame] = 6
                frame += 1
                self.delay_tstates[frame] = 5
                frame += 1
                self.delay_tstates[frame] = 4
                frame += 1
                self.delay_tstates[frame] = 3
                frame += 1
                self.delay_tstates[frame] = 2
                frame += 1
                self.delay_tstates[frame] = 1
                frame += 1
                self.delay_tstates[frame] = 0
                frame += 1
                self.delay_tstates[frame] = 0
        #
        # for i in range(len(self.delay_tstates)):
        #     print(f"{i}={self.delay_tstates[i]}")

    def fetch_opcode(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 4
        else:
            self.tstates += 4

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        t = self.memory.peekb(address)
        return t

    def peekb(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        return self.memory.peekb(address)

    def peeksb(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        return self.memory.peeksb(address)

    def pokeb(self, address: int, value: int) -> None:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        self.memory.pokeb(address, value & 0xFF)

    def peekw(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        lsb = self.memory.peekb(address)

        address = (address + 1) & 0xffff
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        msb = self.memory.peekb(address)

        return (msb << 8) + lsb

    def pokew(self, address: int, value: int) -> None:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        self.memory.pokeb(address, value & 0xff)

        address = (address + 1) & 0xffff
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        self.memory.pokeb(address, (value >> 8))

    def address_on_bus(self, address: int, tstates: int) -> None:
        if 16384 <= address < 32768:
            for i in range(tstates):
                self.tstates += (self.delay_tstates[self.tstates] + 1)
        else:
            self.tstates += tstates

        while self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

    def interrupt_handling_time(self, tstates: int) -> None:
        self.tstates += tstates

        while self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

    def in_port(self, port: int) -> int:
        if 16384 <= port < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 1
        else:
            self.tstates += 1

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        if port & 0x0001 != 0:
            if 16384 <= port < 32768:
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
            else:
                self.tstates += 3
        else:
            self.tstates += self.delay_tstates[self.tstates] + 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

        return self.ports.in_port(port)

    def out_port(self, port: int, value: int):
        if 16384 <= port < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 1
        else:
            self.tstates += 1

        self.ports.out_port(port, value)
        if port & 0x0001 != 0:
            if 16384 <= port < 32768:
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
            else:
                self.tstates += 3
        else:
            self.tstates += self.delay_tstates[self.tstates] + 3

        if self.tstates >= self.screen_byte_tstate[self.next_screen_byte_index]:
            self.update_next_screen_word()
            self.next_screen_byte_index += 1

    def is_active_INT(self) -> bool:
        current = self.tstates
        if current >= TSTATES_PER_INTERRUPT:
            current -= TSTATES_PER_INTERRUPT

        return 0 < current < INTERRUPT_LENGTH


class Spectrum:
    def __init__(self):
        self.keyboard = Keyboard()
        self.ports = Ports(self.keyboard)
        self.memory = Memory()

        self.video = Video(self.memory, self.ports, ratio=2)

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
        # self.video.fill_screen_map()
        self.video.update_zx_screen()
        self.video.update(self.bus_access.frames, self.bus_access.tstates)

    def run(self):
        try:
            while True:
                self.bus_access.next_screen_byte_index = 0
                self.video.start_screen()
                next_stop = FIRST_PIXEL_LINE * TSTATES_PER_LINE
                self.z80.execute(next_stop)
                for line in range(SCREEN_HEIGHT):
                    next_stop += TSTATES_LEFT_BORDER
                    self.z80.execute(next_stop)
                    next_stop += TSTATES_PIXELS
                    self.z80.execute(next_stop)
                    next_stop += TSTATES_RIGHT_BORDER
                    next_stop += TSTATES_RETRACE
                    self.z80.execute(next_stop)

                self.z80.execute(TSTATES_PER_INTERRUPT)
                self.bus_access.end_frame(TSTATES_PER_INTERRUPT)
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

    # load.load_sna(SNADIR + 'Exolon.sna')
    # load.load_sna(SNADIR + 'Batman.sna')
    # load.load_sna(SNADIR + "CHUCKEGG 2.SNA")
    # load.load_sna(SNADIR + 'TheWayOfTheExplodingFist.sna')
    # load.load_sna(SNADIR + 'WorseThingsHappenAtSea.sna')
    # load.load_sna(SNADIR + 'Uridium.sna')
    load.load_sna(SNADIR + 'yazzie.sna')
    # load.load_sna(SNADIR + 'nirvana-demo.sna')
    # load.load_sna(SNADIR + "../../Z80InstructionExerciser_for_the_Spectrum/snapshot1.sna")
    # load.load_sna(SNADIR + "../../Z80InstructionExerciser_for_the_Spectrum/snapshot2.sna")
    # load.load_sna(SNADIR + "../../Z80InstructionExerciser_for_the_Spectrum/snapshot3.sna")
    # load.load_sna(SNADIR + "../../basic1.sna")

    # spectrum.video.fast = True
    # spectrum.z80.show_debug_info = True
    # spectrum.keyboard.do_key(True, 13, 0)

    spectrum.run()
