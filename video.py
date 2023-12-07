import time
from typing import Optional

import pygame

from pygame import Surface

from bus_access import ClockAndBusAccess
from ports import Ports
from memory import Memory

TSTATES_PER_INTERRUPT = 69888
TSTATES_PER_LINE = 224
TSTATES_LEFT_BORDER = 24
TSTATES_RIGHT_BORDER = 24
TSTATES_PIXELS = 128
TSTATES_RETRACE = 48
TSTATES_FIRST_LINE = TSTATES_PER_LINE - TSTATES_LEFT_BORDER
TSTATES_LAST_LINE = TSTATES_RIGHT_BORDER
NUMBER_OF_LINES = 312
FIRST_PIXEL_LINE = 64

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 192
FULL_SCREEN_WIDTH = 384
FULL_SCREEN_HEIGHT = 256
CAPTION = 'PyZX'

COLOR_ON_NORMAL = 205
COLOR_ON_BRIGHT = 255
COLORS = [
    (0, 0, 0),                                            # Black Bright Off
    (0, 0, COLOR_ON_NORMAL),                              # Blue Bright Off
    (COLOR_ON_NORMAL, 0, 0),                              # Red Bright Off
    (COLOR_ON_NORMAL, 0, COLOR_ON_NORMAL),                # Magenta Bright Off
    (0, COLOR_ON_NORMAL, 0),                              # Green Bright Off
    (0, COLOR_ON_NORMAL, COLOR_ON_NORMAL),                # Cyan Bright Off
    (COLOR_ON_NORMAL, COLOR_ON_NORMAL, 0),                # Yellow Bright Off
    (COLOR_ON_NORMAL, COLOR_ON_NORMAL, COLOR_ON_NORMAL),  # White Bright Off

    (0, 0, 0),                                            # Black Bright On
    (0, 0, COLOR_ON_BRIGHT),                              # Blue Bright On
    (COLOR_ON_BRIGHT, 0, 0),                              # Red Bright On
    (COLOR_ON_BRIGHT, 0, COLOR_ON_BRIGHT),                # Magenta Bright On
    (0, COLOR_ON_BRIGHT, 0),                              # Green Bright On
    (0, COLOR_ON_BRIGHT, COLOR_ON_BRIGHT),                # Cyan Bright On
    (COLOR_ON_BRIGHT, COLOR_ON_BRIGHT, 0),                # Yellow Bright On
    (COLOR_ON_BRIGHT, COLOR_ON_BRIGHT, COLOR_ON_BRIGHT)   # White Bright On
]
STRIDE = 256 * 8

SPECTRUM_SCREEN_SIZE = (SCREEN_WIDTH, SCREEN_HEIGHT)
SPECTRUM_FULL_SCREEN_SIZE = (FULL_SCREEN_WIDTH, FULL_SCREEN_HEIGHT)


class Video:
    def __init__(self, bus_access: ClockAndBusAccess, memory: Memory, ports: Ports, show_fps: bool = True, ratio: int = 2):
        self.bus_access = bus_access
        self.memory = memory
        self.ports = ports
        self.ratio = ratio
        self.show_fps = show_fps

        # Initialisation of address tables for pixels and attribute lines
        self.addr_pix = [(((line // 64) * 2048) + ((line % 8) * 256) + ((line & 56) * 4)) for line in range(192)]
        self.addr_attr = [(6144 + ((line // 8) * 32)) for line in range(192)]
        self.zxrowmap = [((coord_y & 0b111) << 3) + ((coord_y & 0b111000) >> 3) + (coord_y & 0b11000000) for coord_y in range(192)]
        self.colormap = [((attr % 8) + (8 if attr & 64 else 0), (attr & 0b1111000) >> 3) for attr in range(256)]

        self.pixelmap = bytearray(256 * 256 * 8)
        self.pixelmap_m = memoryview(self.pixelmap)

        self.offs = 0
        self.pix_addr = 0
        self.attr_addr = 0
        self.pixel_x = 0

        self.zx_screen: Optional[Surface] = None
        self.zx_screen_with_border: Optional[Surface] = None
        self.screen: Optional[Surface] = None
        self.pre_screen: Optional[Surface] = None

        self.video_clock = pygame.time.Clock()
        self.old_border = -1

        self.scaled_spectrum_size = (FULL_SCREEN_WIDTH * self.ratio, FULL_SCREEN_HEIGHT * self.ratio)

        self.buffer_m = memoryview(bytearray(SCREEN_WIDTH * SCREEN_HEIGHT))
        self.back_buffer_m = memoryview(bytearray(SCREEN_WIDTH * SCREEN_HEIGHT))

        self.zx_videoram = self.memory.mem[16384:16384 + 6912]

        self.init_pixelmap()

        self.show_fps = True
        self.fast = False
        self._fast_counter = 0
        self._last_frame = 0
        self._last_tstates = 0
        self._last_time = time.time()

    def init_pixelmap(self):
        for i in range(256):
            color_ink, color_paper = self.colormap[i]
            pixellist = self.pixelmap_m[i * STRIDE:i * STRIDE + STRIDE]
            for pix in range(256):
                pixels = pixellist[pix * 8:pix * 8 + 8]
                for bit in range(8):
                    pixels[7 - bit] = color_ink if (pix & (1 << bit)) else color_paper

    def init(self):
        pygame.init()

        icon = pygame.image.load('icon.png')

        self.zx_screen = pygame.surface.Surface(SPECTRUM_SCREEN_SIZE, pygame.HWSURFACE, 8)
        self.zx_screen.set_palette(COLORS)
        # print(f"zx_screen get depth = {zx_screen.get_bitsize()}")

        self.zx_screen_with_border = pygame.surface.Surface((FULL_SCREEN_WIDTH, FULL_SCREEN_HEIGHT), pygame.HWSURFACE, 8)
        self.zx_screen_with_border.set_palette(COLORS)

        self.pre_screen = pygame.surface.Surface(size=self.scaled_spectrum_size, flags=pygame.HWSURFACE, depth=8)
        self.pre_screen.set_palette(COLORS)

        self.screen = pygame.display.set_mode(size=self.scaled_spectrum_size, flags=pygame.HWSURFACE | pygame.DOUBLEBUF, depth=8)

        # pygame.display.set_palette(COLORS)
        pygame.display.set_caption(CAPTION)
        pygame.display.set_icon(icon)
        pygame.display.flip()

    def update(self):
        # TODO - collect timings of changes of border and recreate it afterwards here
        if self.ports.current_border != self.old_border:
            self.zx_screen_with_border.fill(self.ports.current_border)
            self.old_border = self.ports.current_border

        # self.fill_screen_map()
        self.zx_screen_with_border.blit(self.zx_screen, (64, 32))
        pygame.transform.scale(self.zx_screen_with_border, self.scaled_spectrum_size, self.pre_screen)
        self.screen.blit(self.pre_screen, (0, 0))

        video_frame = False
        if self.fast:
            if self._fast_counter <= 0:
                self.video_clock.tick(50)
                pygame.display.flip()
                self._fast_counter = 200
                video_frame = True
            self._fast_counter -= 1
        else:
            video_frame = True

        if video_frame:
            if self.show_fps:
                now = time.time()
                total_tstates = (self.bus_access.frames - self._last_frame) * TSTATES_PER_INTERRUPT + (self.bus_access.tstates - self._last_tstates)
                speed = (total_tstates / (TSTATES_PER_INTERRUPT * (now - self._last_time) * 50)) * 100

                self._last_frame = self.bus_access.frames
                self._last_tstates = self.bus_access.tstates
                self._last_time = now
                if self.fast:
                    pygame.display.set_caption(f'{CAPTION} - {self.video_clock.get_fps():.2f} FPS, Speed: {speed:0.1f}%')
                else:
                    # pygame.display.set_caption(f'{CAPTION} - Speed: {speed:0.1f}%')
                    pygame.display.set_caption(f'{CAPTION} - {self.video_clock.get_fps():.2f} FPS')

            self.video_clock.tick(50)
            pygame.display.flip()

    def fill_screen_map_line(self, coord_y: int) -> None:
        # zx_videoram = self.memory.mem[16384:16384 + 6912]
        offs = 32 * 8 * coord_y

        pix_addr = self.addr_pix[coord_y]
        attr_addr = self.addr_attr[coord_y]

        for i in range(0, 32):
            poffs = self.zx_videoram[attr_addr + i] * STRIDE + self.zx_videoram[pix_addr + i] * 8
            self.buffer_m[offs:offs + 8] = self.pixelmap_m[poffs:poffs + 8]
            offs += 8

    def start_screen_line(self, line: int) -> None:
        self.offs = 32 * 8 * line
        self.pix_addr = self.addr_pix[line]
        self.attr_addr = self.addr_attr[line]
        self.pixel_x = 0

    def update_next_screen_byte(self) -> None:
        poffs = self.zx_videoram[self.attr_addr + self.pixel_x] * STRIDE + self.zx_videoram[self.pix_addr + self.pixel_x] * 8
        self.buffer_m[self.offs:self.offs + 8] = self.pixelmap_m[poffs:poffs + 8]
        self.offs += 8
        self.pixel_x += 1

    def update_pixel_byte(self, x: int, line: int) -> None:
        offs = 32 * 8 * line + x * 8
        pix_addr = self.addr_pix[line] + x
        attr_addr = self.addr_attr[line] + x

        poffs = self.zx_videoram[attr_addr] * STRIDE + self.zx_videoram[pix_addr] * 8
        self.buffer_m[offs:offs + 8] = self.pixelmap_m[poffs:poffs + 8]

    def fill_screen_map(self) -> None:
        # zx_videoram = self.memory.mem[16384:16384 + 6912]
        offs = 0

        for coord_y in range(SCREEN_HEIGHT):
            pix_addr = self.addr_pix[coord_y]
            attr_addr = self.addr_attr[coord_y]

            for i in range(0, 32):
                poffs = self.zx_videoram[attr_addr + i] * STRIDE + self.zx_videoram[pix_addr + i] * 8
                self.buffer_m[offs:offs + 8] = self.pixelmap_m[poffs:poffs + 8]
                offs += 8

    def update_zx_screen(self) -> None:
        buf = self.zx_screen.get_buffer()
        buf.write(self.buffer_m.tobytes())
