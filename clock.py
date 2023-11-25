
class Clock:
    def __init__(self) -> None:
        self.tstates = 0
        self.frames = 0

    def reset(self) -> None:
        self.tstates = 0

    def end_frame(self, frame_tstates: int) -> None:
        self.tstates -= frame_tstates
        self.frames += 1
