#!/usr/bin/env python3

"""
ZX Spectrum Emulator
Vadim Kataev
www.technopedia.org
"""

import sys

from bus_access import ClockAndBusAccess

from keyboard import Keyboard
from ports import Ports
from memory import Memory
from video import Video, SCREEN_HEIGHT, TSTATES_PER_INTERRUPT, TSTATES_LEFT_BORDER, FIRST_PIXEL_LINE, TSTATES_PER_LINE, TSTATES_PIXELS, TSTATES_RIGHT_BORDER, TSTATES_RETRACE
from z80 import Z80

from load import Load


ROMFILE = '48.rom'
SNADIR = 'games/'

# As per https://worldofspectrum.org/faq/reference/48kreference.htm

INTERRUPT_LENGTH = 24


class ZXSpectrum48ClockAndBusAccess(ClockAndBusAccess):
    def __init__(self,
                 memory: Memory,
                 ports: Ports) -> None:
        super().__init__(memory, ports)

        self.delay_tstates = [0] * (TSTATES_PER_INTERRUPT + 200)

        for i in range(14335, 57247, TSTATES_PER_LINE):
            for n in range(0, 128, 8):
                frame = i + n
                self.delay_tstates[frame] = 6
                frame -= 1
                self.delay_tstates[frame] = 5
                frame -= 1
                self.delay_tstates[frame] = 4
                frame -= 1
                self.delay_tstates[frame] = 3
                frame -= 1
                self.delay_tstates[frame] = 2
                frame -= 1
                self.delay_tstates[frame] = 1
                frame -= 1
                self.delay_tstates[frame] = 0
                frame -= 1
                self.delay_tstates[frame] = 0

    def fetch_opcode(self, address: int) -> int:
        if 16383 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 4
        else:
            self.tstates += 4

        t = self.memory.peekb(address)
        return t

    def peekb(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3
        return self.memory.peekb(address)

    def peeksb(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3
        return self.memory.peeksb(address)

    def pokeb(self, address: int, value: int) -> None:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3
        self.memory.pokeb(address, value & 0xFF)

    def peekw(self, address: int) -> int:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        lsb = self.memory.peekb(address)

        address = (address + 1) & 0xffff
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3
        msb = self.memory.peekb(address)

        return (msb << 8) + lsb

    def pokew(self, address: int, value: int) -> None:
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3

        self.memory.pokeb(address, value & 0xff)

        address = (address + 1) & 0xffff
        if 16384 <= address < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 3
        else:
            self.tstates += 3
        self.memory.pokeb(address, (value >> 8))

    def address_on_bus(self, address: int, tstates: int) -> None:
        if 16384 <= address < 32768:
            for i in range(tstates):
                self.tstates += self.delay_tstates[self.tstates] + 1
        else:
            self.tstates += tstates

    def interrupt_handling_time(self, tstates: int) -> None:
        self.tstates += tstates

    def in_port(self, port: int) -> int:
        if 16384 <= port < 32768:
            self.tstates += self.delay_tstates[self.tstates] + 1
        else:
            self.tstates += 1

        if port & 0x0001 != 0:
            if 16384 <= port < 32768:
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
                self.tstates += self.delay_tstates[self.tstates] + 1
            else:
                self.tstates += 3
        else:
            self.tstates += self.delay_tstates[self.tstates] + 3

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

    def add_tstates(self, int) -> None:
        self.tstates += int

    def is_active_INT(self) -> bool:
        current = self.tstates
        if current >= TSTATES_PER_INTERRUPT:
            current -= TSTATES_PER_INTERRUPT

        return 0 < current < INTERRUPT_LENGTH


class Spectrum:
    def __init__(self):
        # self.step_states = [0] * 6144
        # self.states2screen = [0] * (TSTATES_PER_INTERRUPT + 100)
        # self.scr_addr = [0] * SCREEN_HEIGHT

        self.keyboard = Keyboard()
        self.ports = Ports(self.keyboard)
        self.memory = Memory()

        self.bus_access = ZXSpectrum48ClockAndBusAccess(
            self.memory,
            self.ports)

        self.video = Video(self.bus_access, self.memory, self.ports, ratio=2)

        self.z80 = Z80(
            self.bus_access,
            self.memory)

        self.video_update_time = 0

        self.video.init()

        # Init lookup tables and such
        # for linea in range(24):
        #     lsb = (linea & 0x07) << 5
        #     msb = linea & 0x18
        #     addr = (msb << 8) + lsb
        #     idx = linea << 3
        #
        #     for scan in range(8):
        #         self.scr_addr[scan + idx] = 0x4000 + addr
        #         addr += 256

        # Border left: 32, right: 32, top:24, bottom: 24
        # first_border_update = (FIRST_PIXEL_LINE - 24) * TSTATES_PER_LINE - (32 / 2)
        # last_border_update = (255 + 24) * TSTATES_PER_LINE + 128 + 32

        # firstBorderUpdate = ((64 - screenGeometry.border().top()) * spectrumModel.tstatesLine) - screenGeometry.border().left() / 2;
        # lastBorderUpdate = (255 + screenGeometry.border().bottom()) * spectrumModel.tstatesLine + 128 + screenGeometry.border().right();
        #
        # first_screen_byte = FIRST_PIXEL_LINE * TSTATES_PER_LINE
        #
        # step = 0
        # for tstates in range(first_screen_byte, 57248, 4):
        #     col = (tstates % TSTATES_PER_LINE) / 4
        #     if col <= 31:
        #         scan = tstates // TSTATES_PER_LINE - 64  # UP BORDER WIDTH
        #         self.states2screen[tstates + 2] = self.scr_addr[scan] + col
        #         self.step_states[step] = tstates + 2
        #         step += 1

    def load_rom(self, romfilename):
        """ Load given romfile into memory """

        with open(romfilename, 'rb') as rom:
            rom.readinto(self.memory.mem)

        print('Loaded ROM: %s' % romfilename)

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
        self.video.update()

    def run(self):
        """ Start the execution """
        try:
            while True:
                next_stop = FIRST_PIXEL_LINE * TSTATES_PER_LINE
                self.z80.execute(next_stop)
                for line in range(SCREEN_HEIGHT):
                    next_stop += TSTATES_LEFT_BORDER
                    self.z80.execute(next_stop)
                    next_stop += TSTATES_PIXELS
                    self.z80.execute(next_stop)
                    # self.video.fill_screen_map_line(line)
                    # for x in range(32):
                    #     self.video.update_pixel_byte(x, line)
                    self.video.start_screen_line(line)
                    for x in range(32):
                        self.video.update_next_screen_byte()
                    next_stop += TSTATES_RIGHT_BORDER
                    next_stop += TSTATES_RETRACE
                    self.z80.execute(next_stop)

                self.z80.execute(TSTATES_PER_INTERRUPT)

                # while self.tstates < TSTATES_PER_INTERRUPT:
                #     self.z80.execute_one_cycle()
                self.bus_access.end_frame(TSTATES_PER_INTERRUPT)
                # self.video.fill_screen_map()
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
