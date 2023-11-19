import struct


class Memory:
    def __init__(self):
        # ** Memory
        self.mem = memoryview(bytearray(65536))

        self.mem_rw = [False, True, True, True]

        # Word access
        self.wstruct = struct.Struct('<H')
        # Signed byte access
        self.signedbyte = struct.Struct('<b')

    def pokew(self, addr: int, word):
        if addr % 0x4000 == 0x3fff:
            if self.mem_rw[addr//0x4000]:
                self.mem[addr] = word % 256
            addr = (addr + 1) % 65536
            if self.mem_rw[addr//0x4000]:
                self.mem[addr] = word >> 8
        else:
            if self.mem_rw[addr//0x4000]:
                self.wstruct.pack_into(self.mem, addr, word)

    def peekw(self, addr: int) -> int:
        if addr == 65535:
            return (self.mem[65535] | (self.mem[0] << 8)) % 65536

        return self.wstruct.unpack_from(self.mem, addr)[0]

    def pokeb(self, addr: int, byte):
        try:
            if self.mem_rw[addr//0x4000]:
                self.mem[addr] = byte
        except Exception as error:
            print(addr, byte, type(addr), type(byte))
            raise error

    def peekb(self, addr: int) -> int:
        return self.mem[addr]

    def peeksb(self, addr: int) -> int:
        return self.signedbyte.unpack_from(self.mem, addr)[0]


if __name__ == '__main__':
    memory = Memory()
    memory.pokeb(100000, 111)
    print('DONE')
