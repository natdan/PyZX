from typing import Callable

from spectrum.video import TSTATES_PER_INTERRUPT, TSTATES_PER_LINE, SCREEN_HEIGHT, SCREEN_WIDTH
from z80.bus_access import ClockAndBusAccess
from z80.memory import Memory
from z80.ports import Ports


INTERRUPT_LENGTH = 24


class ZXSpectrum48ClockAndBusAccess(ClockAndBusAccess):
    def __init__(self,
                 memory: Memory,
                 ports: Ports,
                 update_next_screen_byte: Callable) -> None:
        super().__init__(memory, ports)
        self.frames = 0

        self.int_line = False
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

    def end_frame(self, frame_tstates: int) -> None:
        self.tstates -= frame_tstates
        self.frames += 1

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
                self.tstates += self.delay_tstates[self.tstates] + 1
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

        self.int_line = 0 < current < INTERRUPT_LENGTH
        return self.int_line
