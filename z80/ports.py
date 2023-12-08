class Ports:
    def in_port(self, _portnum: int) -> int:
        return 0xff

    def out_port(self, portnum: int, data: int):
        pass
