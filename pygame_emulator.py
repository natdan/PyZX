from typing import Optional

import time

import pygame
from pygame import Surface

from spectrum.keyboard import Keyboard
from spectrum.machine import Spectrum
from spectrum.spectrum_bus_access import ZXSpectrum48ClockAndBusAccess
from spectrum.video import COLORS, TSTATES_PER_INTERRUPT, FULL_SCREEN_WIDTH, FULL_SCREEN_HEIGHT, Video

CAPTION = "ZX Spectrum 48k Emulator"


class PyGameEmulator:
    def __init__(self, spectrum: Spectrum, show_fps: bool = True, ratio: int = 3) -> None:
        self.show_fps = show_fps
        self.ratio = ratio

        self.machine = spectrum
        self.video: Video = spectrum.video
        self.keyboard: Keyboard = spectrum.keyboard
        self.bus_access: ZXSpectrum48ClockAndBusAccess = spectrum.bus_access

        self.video_clock = pygame.time.Clock()

        self.screen: Optional[Surface] = None
        self.pre_screen: Optional[Surface] = None
        self.scaled_spectrum_size = (FULL_SCREEN_WIDTH * self.ratio, FULL_SCREEN_HEIGHT * self.ratio)

        self.fast = False
        self.show_fps = True
        self.fast = False
        self._fast_counter = 0
        self._last_frame = 0
        self._last_tstates = 0
        self._last_time = time.time()
        self.spare_time = [0] * 50

    def init(self) -> None:
        pygame.init()
        icon = pygame.image.load('icon.png')

        self.screen = pygame.display.set_mode(size=self.scaled_spectrum_size, flags=pygame.HWSURFACE | pygame.DOUBLEBUF, depth=8)
        self.pre_screen = pygame.surface.Surface(size=self.scaled_spectrum_size, flags=pygame.HWSURFACE, depth=8)
        self.pre_screen.set_palette(COLORS)

        pygame.display.set_caption(CAPTION)
        pygame.display.set_icon(icon)
        pygame.display.flip()

    def update(self, frames: int, tstates: int) -> None:
        pygame.transform.scale(self.machine.video.zx_screen_with_border, self.scaled_spectrum_size, self.pre_screen)
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

        now = time.time()
        self.video_clock.tick(50)

        if video_frame:
            if self.show_fps:
                total_tstates = (frames - self._last_frame) * TSTATES_PER_INTERRUPT + (tstates - self._last_tstates)
                speed = (total_tstates / (TSTATES_PER_INTERRUPT * (now - self._last_time) * 50)) * 100

                self._last_frame = frames
                self._last_tstates = tstates
                self._last_time = now

                time_difference = time.time() - now
                self.spare_time[0:-1] = self.spare_time[1:]
                self.spare_time[-1] = int(time_difference * 100000 / 20)
                spare_time = int(sum(self.spare_time) / len(self.spare_time))

                if self.fast:
                    pygame.display.set_caption(f'{CAPTION} - {self.video_clock.get_fps():.2f} FPS, Speed: {speed:0.1f}%')
                else:
                    # pygame.display.set_caption(f'{CAPTION} - Speed: {speed:0.1f}%')
                    pygame.display.set_caption(f'{CAPTION} - {self.video_clock.get_fps():.2f} FPS, {spare_time: 4}%')

            pygame.display.flip()

    def process_interrupt(self):
        self.machine.bus_access.end_frame(TSTATES_PER_INTERRUPT)

        pygame.event.pump()
        mods = pygame.key.get_mods()
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                self.keyboard.do_key(True, event.key, mods)
            elif event.type == pygame.KEYUP:
                self.keyboard.do_key(False, event.key, mods)
            elif event.type == pygame.QUIT:
                raise KeyboardInterrupt()

        self.video.finish_screen()
        self.video.update()
        self.update(self.bus_access.frames, self.bus_access.tstates)
        self.video.start_screen()

    def run(self):
        try:
            while True:
                self.machine.z80.execute(TSTATES_PER_INTERRUPT)
                self.process_interrupt()
        except KeyboardInterrupt:
            return
