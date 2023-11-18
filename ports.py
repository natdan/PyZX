# -*- coding: utf-8 -*-
from keyboard import Keyboard


class Ports:
    def __init__(self, keyboard: Keyboard):
        self.keyboard = keyboard
        self.current_border = 0

        self.PORTMAP = [
            (0x0001, 0x00fe, 2, 2, 2, self.xInFE, self.xOutFE),  # keyboard
            # (0xc002, 0xfffd, 2, 2, 2, xInFFFD, xOutFFFD),
            # (0xc002, 0xbffd, 2, 2, 2, None, xOutBFFD),      # AYdataW
            # (0x0320, 0xfadf, 2, 2, 2, xInFADF, None),       # K-MOUSEturboB
            # (0x0720, 0xfbdf, 2, 2, 2, xInFBDF, None),       # K-MOUSE_X
            # (0x0720, 0xffdf, 2, 2, 2, xInFFDF, None),      # K-MOUSE_Y
            (0x0021, 0x001f, 0, 2, 2, self.spIn1F, None),  # kempstom joystick
            (0x0000, 0x0000, 0, 2, 2, self.spInFF, None),  # all unknown ports is FF (nodos)
            (0x0000, 0x0000, 2, 2, 2, self.spInFF, None)
        ]

    def xInFE(self, port: int) -> int:
        res = 0xff
        k = self.keyboard.keyboard
        if (port & 0x8000) == 0:
            res &= k[0]  # _B_SPC
        if (port & 0x4000) == 0:
            res &= k[1]  # _H_ENT
        if (port & 0x2000) == 0:
            res &= k[2]  # _Y_P
        if (port & 0x1000) == 0:
            res &= k[3]  # _6_0
        if (port & 0x0800) == 0:
            res &= k[4]  # _1_5
        if (port & 0x0400) == 0:
            res &= k[5]  # _Q_T
        if (port & 0x0200) == 0:
            res &= k[6]  # _A_G
        if (port & 0x0100) == 0:
            res &= k[7]  # _CAPS_V
        return res

    def xOutFE(self, _port: int, value: int):
        self.current_border = value & 0x07

    @staticmethod
    def xInFFFD(_port: int) -> int:
        return 0xff

    @staticmethod
    def xOutFFFD(_port: int, _value: int):
        return 0xff

    @staticmethod
    def xOutBFFD(_port: int, _value: int):
        return 0xff

    @staticmethod
    def xInFADF(_port: int) -> int:
        return 0xff

    @staticmethod
    def xInFBDF(_port: int) -> int:
        return 0xff

    @staticmethod
    def xInFFDF(_port: int) -> int:
        return 0xff

    def spIn1F(self, _port: int) -> int:
        return self.keyboard.joy[0]

    @staticmethod
    def spInFF(_port: int) -> int:
        return 0xff

    def port_in(self, portnum: int) -> int:
        # print('port: ', portnum, type(portnum))
        for mask, value, _, _, _, fin, _ in self.PORTMAP:
            if portnum & mask == value & mask:
                return fin(portnum) if fin else 0xff
        return 0xff

    def port_out(self, portnum: int, data: int):
        for mask, value, _, _, _, _, fout in self.PORTMAP:
            if portnum & mask == value & mask:
                if fout:
                    fout(portnum, data)
                break
