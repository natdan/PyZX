from memory import Memory
from ports import Ports


class ClockAndBusAccess:
    def __init__(self,
                 memory: Memory,
                 ports: Ports) -> None:
        self.tstates = 0
        self.frames = 0
        self.memory = memory
        self.ports = ports

    def reset(self) -> None:
        self.tstates = 0

    def end_frame(self, frame_tstates: int) -> None:
        self.tstates -= frame_tstates
        self.frames += 1

    def fetch_opcode(self, address: int) -> int:
        t = self.memory.peekb(address)
        self.tstates += 4
        return t

    def peekb(self, address: int) -> int:
        self.tstates += 3
        return self.memory.peekb(address)

    def peeksb(self, address: int) -> int:
        self.tstates += 3
        return self.memory.peeksb(address)

    def pokeb(self, address: int, value: int) -> None:
        self.tstates += 3
        self.memory.pokeb(address, value & 0xFF)

    def peekw(self, address: int) -> int:
        lsb = self.peekb(address)
        msb = self.peekb((address + 1) & 0xFFFF)

        return (msb << 8) | lsb

    def pokew(self, address: int, value: int) -> None:
        self.memory.pokeb(address, value & 0xff)
        self.memory.pokeb(address + 1, (value >> 8))

    def address_on_bus(self, address: int, tstates: int) -> None:
        self.tstates += tstates

    def interrupt_handling_time(self, tstates: int) -> None:
        self.tstates += tstates

    def in_port(self, port: int) -> int:
        self.tstates += 4
        return self.ports.in_port(port)

    def out_port(self, port: int, value: int):
        self.tstates += 4
        self.ports.out_port(port, value)

    def is_active_INT(self) -> bool:
        return False
