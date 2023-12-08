from spectrum.machine import Spectrum
from utils.load import Load


spectrum = Spectrum()
spectrum.init()
load = Load(spectrum.z80, spectrum.ports)

# spectrum.video.fast = True
# spectrum.z80.show_debug_info = True
# spectrum.keyboard.do_key(True, 13, 0)

spectrum.run()
