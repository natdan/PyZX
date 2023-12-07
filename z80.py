from typing import Callable

from bus_access import ClockAndBusAccess
from memory import Memory


IM0 = 0
IM1 = 1
IM2 = 2

CARRY_MASK = 0x01
ADDSUB_MASK = 0x02
PARITY_MASK = 0x04
OVERFLOW_MASK = 0x04  # alias de PARITY_MASK
BIT3_MASK = 0x08
HALFCARRY_MASK = 0x10
BIT5_MASK = 0x20
ZERO_MASK = 0x40
SIGN_MASK = 0x80

FLAG_53_MASK = BIT5_MASK | BIT3_MASK
FLAG_SZ_MASK = SIGN_MASK | ZERO_MASK
FLAG_SZHN_MASK = FLAG_SZ_MASK | HALFCARRY_MASK | ADDSUB_MASK
FLAG_SZP_MASK = FLAG_SZ_MASK | PARITY_MASK
FLAG_SZHP_MASK = FLAG_SZP_MASK | HALFCARRY_MASK


class Z80:
    def __init__(self,
                 bus_access: ClockAndBusAccess,
                 memory: Memory) -> None:
        self.bus_access = bus_access
        self.memory = memory

        self.show_debug_info = False

        self.bus_access.tstates = 0

        self._prefixOpcode = 0x00
        self.execDone = False

        self.regA = 0
        self.regB = 0
        self.regC = 0
        self.regD = 0
        self.regE = 0
        self.regH = 0
        self.regL = 0
        self._sz5h3pnFlags = 0
        self.carryFlag = False
        self._flagQ = False
        self._lastFlagQ = False

        self.regAx = 0
        self.regFx = 0
        self.regBx = 0
        self.regCx = 0
        self.regDx = 0
        self.regEx = 0
        self.regHx = 0
        self.regLx = 0

        self.regPC = 0
        self.regIX = 0
        self.regIY = 0
        self.regSP = 0
        self.regI = 0
        self.regR = 0
        self.regRbit7 = False
        self.ffIFF1 = False
        self.ffIFF2 = False
        self.pendingEI = False
        self.activeNMI = False
        self.activeINT = False
        self.modeINT = IM0
        self.halted = False
        self.pinReset = False
        self.memptr = 0

        self._sz53n_addTable = [0] * 256
        self._sz53pn_addTable = [0] * 256
        self._sz53n_subTable = [0] * 256
        self._sz53pn_subTable = [0] * 256

        self.breakpointAt = [False] * 65536

        for idx in range(256):
            if idx > 0x7f:
                self._sz53n_addTable[idx] |= SIGN_MASK

            evenBits = True
            mask = 0x01
            while mask < 0x100:
                if (idx & mask) != 0:
                    evenBits = not evenBits
                mask = mask << 1

            self._sz53n_addTable[idx] |= (idx & FLAG_53_MASK)
            self._sz53n_subTable[idx] = self._sz53n_addTable[idx] | ADDSUB_MASK

            if evenBits:
                self._sz53pn_addTable[idx] = self._sz53n_addTable[idx] | PARITY_MASK
                self._sz53pn_subTable[idx] = self._sz53n_subTable[idx] | PARITY_MASK
            else:
                self._sz53pn_addTable[idx] = self._sz53n_addTable[idx]
                self._sz53pn_subTable[idx] = self._sz53n_subTable[idx]

        self._sz53n_addTable[0] |= ZERO_MASK
        self._sz53pn_addTable[0] |= ZERO_MASK
        self._sz53n_subTable[0] |= ZERO_MASK
        self._sz53pn_subTable[0] |= ZERO_MASK

        self._main_cmds = {
            0x00: self._nop, 0x08: self._ex_af_af, 0x10: self._djnz, 0x18: self._jr, 0x20: self._jrnz, 0x28: self._jrz, 0x30: self._jrnc, 0x38: self._jrc,
            0x01: self._ldbcnn, 0x09: self._addhlbc, 0x11: self._lddenn, 0x19: self._addhlde, 0x21: self._ldhlnn, 0x29: self._addhlhl, 0x31: self._ldspnn, 0x39: self._addhlsp,
            0x02: self._ldtobca, 0x0a: self._ldafrombc, 0x12: self._ldtodea, 0x1a: self._ldafromde, 0x22: self._ldtonnhl, 0x2a: self._ldhlfromnn, 0x32: self._ldtonna, 0x3a: self._ldafromnn,
            0x03: self._incbc, 0x0b: self._decbc, 0x13: self._incde, 0x1b: self._decde, 0x23: self._inchl, 0x2b: self._dechl, 0x33: self._incsp, 0x3b: self._decsp,
            0x04: self._incb, 0x0c: self._incc, 0x14: self._incd, 0x1c: self._ince, 0x24: self._inch, 0x2c: self._incl, 0x34: self._incinhl, 0x3c: self._inca,
            0x05: self._decb, 0x0d: self._decc, 0x15: self._decd, 0x1d: self._dece, 0x25: self._dech, 0x2d: self._decl, 0x35: self._decinhl, 0x3d: self._deca,
            0x06: self._ldbn, 0x0e: self._ldcn, 0x16: self._lddn, 0x1e: self._lden, 0x26: self._ldhn, 0x2e: self._ldln, 0x36: self._ldtohln, 0x3e: self._ldan,
            0x07: self._rlca, 0x0f: self._rrca, 0x17: self._rla, 0x1f: self._rra, 0x27: self._daa, 0x2f: self._cpla, 0x37: self._scf, 0x3f: self._ccf,
            0x40: self._ldbb, 0x41: self._ldbc, 0x42: self._ldbd, 0x43: self._ldbe, 0x44: self._ldbh, 0x45: self._ldbl, 0x46: self._ldbfromhl, 0x47: self._ldba,
            0x48: self._ldcb, 0x49: self._ldcc, 0x4a: self._ldcd, 0x4b: self._ldce, 0x4c: self._ldch, 0x4d: self._ldcl, 0x4e: self._ldcfromhl, 0x4f: self._ldca,
            0x50: self._lddb, 0x51: self._lddc, 0x52: self._lddd, 0x53: self._ldde, 0x54: self._lddh, 0x55: self._lddl, 0x56: self._lddfromhl, 0x57: self._ldda,
            0x58: self._ldeb, 0x59: self._ldec, 0x5a: self._lded, 0x5b: self._ldee, 0x5c: self._ldeh, 0x5d: self._ldel, 0x5e: self._ldefromhl, 0x5f: self._ldea,
            0x60: self._ldhb, 0x61: self._ldhc, 0x62: self._ldhd, 0x63: self._ldhe, 0x64: self._ldhh, 0x65: self._ldhl, 0x66: self._ldhfromhl, 0x67: self._ldha,
            0x68: self._ldlb, 0x69: self._ldlc, 0x6a: self._ldld, 0x6b: self._ldle, 0x6c: self._ldlh, 0x6d: self._ldll, 0x6e: self._ldlfromhl, 0x6f: self._ldla,
            0x70: self._ldtohlb, 0x71: self._ldtohlc, 0x72: self._ldtohld, 0x73: self._ldtohle, 0x74: self._ldtohlh, 0x75: self._ldtohll, 0x76: self._halt, 0x77: self._ldtohla,
            0x78: self._ldab, 0x79: self._ldac, 0x7a: self._ldad, 0x7b: self._ldae, 0x7c: self._ldah, 0x7d: self._ldal, 0x7e: self._ldafromhl, 0x7f: self._ldaa,
            0x80: self._addab, 0x81: self._addac, 0x82: self._addad, 0x83: self._addae, 0x84: self._addah, 0x85: self._addal, 0x86: self._addafromhl, 0x87: self._addaa,
            0x88: self._adcab, 0x89: self._adcac, 0x8a: self._adcad, 0x8b: self._adcae, 0x8c: self._adcah, 0x8d: self._adcal, 0x8e: self._adcafromhl, 0x8f: self._adcaa,
            0x90: self._subab, 0x91: self._subac, 0x92: self._subad, 0x93: self._subae, 0x94: self._subah, 0x95: self._subal, 0x96: self._subafromhl, 0x97: self._subaa,
            0x98: self._sbcab, 0x99: self._sbcac, 0x9a: self._sbcad, 0x9b: self._sbcae, 0x9c: self._sbcah, 0x9d: self._sbcal, 0x9e: self._sbcafromhl, 0x9f: self._sbcaa,
            0xa0: self._andab, 0xa1: self._andac, 0xa2: self._andad, 0xa3: self._andae, 0xa4: self._andah, 0xa5: self._andal, 0xa6: self._andafromhl, 0xa7: self._andaa,
            0xa8: self._xorab, 0xa9: self._xorac, 0xaa: self._xorad, 0xab: self._xorae, 0xac: self._xorah, 0xad: self._xoral, 0xae: self._xorafromhl, 0xaf: self._xoraa,
            0xb0: self._orab, 0xb1: self._orac, 0xb2: self._orad, 0xb3: self._orae, 0xb4: self._orah, 0xb5: self._oral, 0xb6: self._orafromhl, 0xb7: self._oraa,
            0xb8: self._cpab, 0xb9: self._cpac, 0xba: self._cpad, 0xbb: self._cpae, 0xbc: self._cpah, 0xbd: self._cpal, 0xbe: self._cpafromhl, 0xbf: self._cpaa,
            0xc0: self._retnz, 0xc8: self._retz, 0xd0: self._retnc, 0xd8: self._retc, 0xe0: self._retpo, 0xe8: self._retpe, 0xf0: self._retp, 0xf8: self._retm,
            0xc1: self._popbc, 0xd1: self._popde, 0xe1: self._pophl, 0xf1: self._popaf,
            0xc2: self._jpnznn, 0xca: self._jpznn, 0xd2: self._jpncnn, 0xda: self._jpcnn, 0xe2: self._jpponn, 0xea: self._jppenn, 0xf2: self._jppnn, 0xfa: self._jpmnn,
            0xd9: self._exx, 0xe9: self._jphl, 0xf9: self._ldsphl, 0xc9: self._ret, 0xc3: self._jpnn, 0xcb: self._cb, 0xd3: self._outna, 0xdb: self._inan, 0xe3: self._exsphl,
            0xeb: self._exdehl, 0xf3: self._di, 0xfb: self._ei,
            0xc4: self._callnznn, 0xcc: self._callznn, 0xd4: self._callncnn, 0xdc: self._callcnn, 0xe4: self._callponn, 0xec: self._callpenn, 0xf4: self._callpnn, 0xfc: self._callmnn,
            0xc5: self._pushbc, 0xd5: self._pushde, 0xe5: self._pushhl, 0xf5: self._pushaf,
            0xc6: self._addan, 0xce: self._adcan, 0xd6: self._suban, 0xde: self._sbcan, 0xe6: self._andan, 0xee: self._xoran, 0xf6: self._oran, 0xfe: self._cpan,
            0xc7: self._rst0, 0xcf: self._rst8, 0xd7: self._rst16, 0xdf: self._rst24, 0xe7: self._rst32, 0xef: self._rst40, 0xf7: self._rst48, 0xff: self._rst56,
            0xcd: self._callnn, 0xdd: self._ix, 0xed: self._ed, 0xfd: self._iy,
        }

        self._cbdict = {
            0x00: self._rlcb, 0x01: self._rlcc, 0x02: self._rlcd, 0x03: self._rlce, 0x04: self._rlch, 0x05: self._rlcl, 0x06: self._rlcfromhl, 0x07: self._rlc_a,
            0x08: self._rrcb, 0x09: self._rrcc, 0x0a: self._rrcd, 0x0b: self._rrce, 0x0c: self._rrch, 0x0d: self._rrcl, 0x0e: self._rrcfromhl, 0x0f: self._rrc_a,
            0x10: self._rlb, 0x11: self._rl_c, 0x12: self._rld_, 0x13: self._rle, 0x14: self._rlh, 0x15: self._rll, 0x16: self._rlfromhl, 0x17: self._rl_a,
            0x18: self._rrb, 0x19: self._rr_c, 0x1a: self._rrd_, 0x1b: self._rre, 0x1c: self._rrh, 0x1d: self._rrl, 0x1e: self._rrfromhl, 0x1f: self._rr_a,
            0x20: self._slab, 0x21: self._slac, 0x22: self._slad, 0x23: self._slae, 0x24: self._slah, 0x25: self._slal, 0x26: self._slafromhl, 0x27: self._sla_a,
            0x28: self._srab, 0x29: self._srac, 0x2a: self._srad, 0x2b: self._srae, 0x2c: self._srah, 0x2d: self._sral, 0x2e: self._srafromhl, 0x2f: self._sra_a,
            0x30: self._slsb, 0x31: self._slsc, 0x32: self._slsd, 0x33: self._slse, 0x34: self._slsh, 0x35: self._slsl, 0x36: self._slsfromhl, 0x37: self._sls_a,
            0x38: self._srlb, 0x39: self._srlc, 0x3a: self._srld, 0x3b: self._srle, 0x3c: self._srlh, 0x3d: self._srll, 0x3e: self._srlfromhl, 0x3f: self._srl_a,

            0x40: self._bit0b, 0x41: self._bit0c, 0x42: self._bit0d, 0x43: self._bit0e, 0x44: self._bit0h, 0x45: self._bit0l, 0x46: self._bit0fromhl, 0x47: self._bit0a,
            0x48: self._bit1b, 0x49: self._bit1c, 0x4a: self._bit1d, 0x4b: self._bit1e, 0x4c: self._bit1h, 0x4d: self._bit1l, 0x4e: self._bit1fromhl, 0x4f: self._bit1a,
            0x50: self._bit2b, 0x51: self._bit2c, 0x52: self._bit2d, 0x53: self._bit2e, 0x54: self._bit2h, 0x55: self._bit2l, 0x56: self._bit2fromhl, 0x57: self._bit2a,
            0x58: self._bit3b, 0x59: self._bit3c, 0x5a: self._bit3d, 0x5b: self._bit3e, 0x5c: self._bit3h, 0x5d: self._bit3l, 0x5e: self._bit3fromhl, 0x5f: self._bit3a,
            0x60: self._bit4b, 0x61: self._bit4c, 0x62: self._bit4d, 0x63: self._bit4e, 0x64: self._bit4h, 0x65: self._bit4l, 0x66: self._bit4fromhl, 0x67: self._bit4a,
            0x68: self._bit5b, 0x69: self._bit5c, 0x6a: self._bit5d, 0x6b: self._bit5e, 0x6c: self._bit5h, 0x6d: self._bit5l, 0x6e: self._bit5fromhl, 0x6f: self._bit5a,
            0x70: self._bit6b, 0x71: self._bit6c, 0x72: self._bit6d, 0x73: self._bit6e, 0x74: self._bit6h, 0x75: self._bit6l, 0x76: self._bit6fromhl, 0x77: self._bit6a,
            0x78: self._bit7b, 0x79: self._bit7c, 0x7a: self._bit7d, 0x7b: self._bit7e, 0x7c: self._bit7h, 0x7d: self._bit7l, 0x7e: self._bit7fromhl, 0x7f: self._bit7a,

            0x80: self._res0b, 0x81: self._res0c, 0x82: self._res0d, 0x83: self._res0e, 0x84: self._res0h, 0x85: self._res0l, 0x86: self._res0fromhl, 0x87: self._res0a,
            0x88: self._res1b, 0x89: self._res1c, 0x8a: self._res1d, 0x8b: self._res1e, 0x8c: self._res1h, 0x8d: self._res1l, 0x8e: self._res1fromhl, 0x8f: self._res1a,
            0x90: self._res2b, 0x91: self._res2c, 0x92: self._res2d, 0x93: self._res2e, 0x94: self._res2h, 0x95: self._res2l, 0x96: self._res2fromhl, 0x97: self._res2a,
            0x98: self._res3b, 0x99: self._res3c, 0x9a: self._res3d, 0x9b: self._res3e, 0x9c: self._res3h, 0x9d: self._res3l, 0x9e: self._res3fromhl, 0x9f: self._res3a,
            0xa0: self._res4b, 0xa1: self._res4c, 0xa2: self._res4d, 0xa3: self._res4e, 0xa4: self._res4h, 0xa5: self._res4l, 0xa6: self._res4fromhl, 0xa7: self._res4a,
            0xa8: self._res5b, 0xa9: self._res5c, 0xaa: self._res5d, 0xab: self._res5e, 0xac: self._res5h, 0xad: self._res5l, 0xae: self._res5fromhl, 0xaf: self._res5a,
            0xb0: self._res6b, 0xb1: self._res6c, 0xb2: self._res6d, 0xb3: self._res6e, 0xb4: self._res6h, 0xb5: self._res6l, 0xb6: self._res6fromhl, 0xb7: self._res6a,
            0xb8: self._res7b, 0xb9: self._res7c, 0xba: self._res7d, 0xbb: self._res7e, 0xbc: self._res7h, 0xbd: self._res7l, 0xbe: self._res7fromhl, 0xbf: self._res7a,

            0xc0: self._set0b, 0xc1: self._set0c, 0xc2: self._set0d, 0xc3: self._set0e, 0xc4: self._set0h, 0xc5: self._set0l, 0xc6: self._set0fromhl, 0xc7: self._set0a,
            0xc8: self._set1b, 0xc9: self._set1c, 0xca: self._set1d, 0xcb: self._set1e, 0xcc: self._set1h, 0xcd: self._set1l, 0xce: self._set1fromhl, 0xcf: self._set1a,
            0xd0: self._set2b, 0xd1: self._set2c, 0xd2: self._set2d, 0xd3: self._set2e, 0xd4: self._set2h, 0xd5: self._set2l, 0xd6: self._set2fromhl, 0xd7: self._set2a,
            0xd8: self._set3b, 0xd9: self._set3c, 0xda: self._set3d, 0xdb: self._set3e, 0xdc: self._set3h, 0xdd: self._set3l, 0xde: self._set3fromhl, 0xdf: self._set3a,
            0xe0: self._set4b, 0xe1: self._set4c, 0xe2: self._set4d, 0xe3: self._set4e, 0xe4: self._set4h, 0xe5: self._set4l, 0xe6: self._set4fromhl, 0xe7: self._set4a,
            0xe8: self._set5b, 0xe9: self._set5c, 0xea: self._set5d, 0xeb: self._set5e, 0xec: self._set5h, 0xed: self._set5l, 0xee: self._set5fromhl, 0xef: self._set5a,
            0xf0: self._set6b, 0xf1: self._set6c, 0xf2: self._set6d, 0xf3: self._set6e, 0xf4: self._set6h, 0xf5: self._set6l, 0xf6: self._set6fromhl, 0xf7: self._set6a,
            0xf8: self._set7b, 0xf9: self._set7c, 0xfa: self._set7d, 0xfb: self._set7e, 0xfc: self._set7h, 0xfd: self._set7l, 0xfe: self._set7fromhl, 0xff: self._set7a
        }

        self._eddict = {
            0x40: self._inbfrombc, 0x48: self._incfrombc, 0x50: self._indfrombc, 0x58: self._inefrombc, 0x60: self._inhfrombc, 0x68: self._inlfrombc, 0x70: self._infrombc, 0x78: self._inafrombc,
            0x41: self._outtocb, 0x49: self._outtocc, 0x51: self._outtocd, 0x59: self._outtoce, 0x61: self._outtoch, 0x69: self._outtocl, 0x71: self._outtoc0, 0x79: self._outtoca,
            0x42: self._sbchlbc, 0x4a: self._adchlbc, 0x52: self._sbchlde, 0x5a: self._adchlde, 0x62: self._sbchlhl, 0x6a: self._adchlhl, 0x72: self._sbchlsp, 0x7a: self._adchlsp,
            0x43: self._ldtonnbc, 0x4b: self._ldbcfromnn, 0x53: self._ldtonnde, 0x5b: self._lddefromnn, 0x63: self._edldtonnhl, 0x6b: self._edldhlfromnn, 0x73: self._ldtonnsp, 0x7b: self._ldspfromnn,
            0x44: self._nega, 0x4c: self._nega, 0x54: self._nega, 0x5c: self._nega, 0x64: self._nega, 0x6c: self._nega, 0x74: self._nega, 0x7c: self._nega,
            0x45: self._retn, 0x55: self._retn, 0x65: self._retn, 0x75: self._retn, 0x4d: self._reti, 0x5d: self._reti, 0x6d: self._reti, 0x7d: self._reti,
            0x46: self._im0, 0x4e: self._im0, 0x66: self._im0, 0x6e: self._im0, 0x56: self._im1, 0x76: self._im1, 0x5e: self._im2, 0x7e: self._im2,
            0x47: self._ldia, 0x4f: self._ldra, 0x57: self._ldai, 0x5f: self._ldar, 0x67: self._rrd, 0x6f: self._rld,
            0xa0: self._ldi, 0xa1: self._cpi, 0xa2: self._ini, 0xa3: self._outi,
            0xa8: self._ldd, 0xa9: self._cpd, 0xaa: self._ind, 0xab: self._outd,
            0xb0: self._ldir, 0xb1: self._cpir, 0xb2: self._inir, 0xb3: self._otir,
            0xb8: self._lddr, 0xb9: self._cpdr, 0xba: self._indr, 0xbb: self._otdr,
            0xdd: self._opcodedd, 0xed: self._opcodeed, 0xfd: self._opcodefd
        }

        self._ixiydict: dict[int, Callable[[int], int]] = {
            0x09: self._addidbc, 0x19: self._addidde, 0x29: self._addidid, 0x39: self._addidsp,
            0x21: self._ldidnn, 0x22: self._ldtonnid, 0x2a: self._ldidfromnn,
            0x23: self._incid, 0x24: self._incidh, 0x2c: self._incidl, 0x34: self._incinidd,
            0x2b: self._decid, 0x25: self._decidh, 0x2d: self._decidl, 0x35: self._decinidd,
            0x44: self._ldbidh, 0x4c: self._ldcidh, 0x54: self._lddidh, 0x5c: self._ldeidh, 0x7c: self._ldaidh,
            0x45: self._ldbidl, 0x4d: self._ldcidl, 0x55: self._lddidl, 0x5d: self._ldeidl, 0x7d: self._ldaidl,
            0x60: self._ldidhb, 0x61: self._ldidhc, 0x62: self._ldidhd, 0x63: self._ldidhe, 0x64: self._ldidhidh, 0x65: self._ldidhidl, 0x26: self._ldidhn, 0x67: self._ldidha,
            0x68: self._ldidlb, 0x69: self._ldidlc, 0x6a: self._ldidld, 0x6b: self._ldidle, 0x6c: self._ldidlidh, 0x6d: self._ldidlidl, 0x2e: self._ldidln, 0x6f: self._ldidla,
            0x46: self._ldbfromidd, 0x4e: self._ldcfromidd, 0x56: self._lddfromidd, 0x5e: self._ldefromidd, 0x66: self._ldhfromidd, 0x6e: self._ldlfromidd, 0x7e: self._ldafromidd,
            0x70: self._ldtoiddb, 0x71: self._ldtoiddc, 0x72: self._ldtoiddd, 0x73: self._ldtoidde, 0x74: self._ldtoiddh, 0x75: self._ldtoiddl, 0x36: self._ldtoiddn, 0x77: self._ldtoidda,
            0x84: self._addaidh, 0x85: self._addaidl, 0x86: self._addafromidd, 0x8c: self._adcaidh, 0x8d: self._adcaidl, 0x8e: self._adcafromidd,
            0x94: self._subaidh, 0x95: self._subaidl, 0x96: self._subafromidd, 0x9c: self._sbcaidh, 0x9d: self._sbcaidl, 0x9e: self._sbcafromidd,
            0xa4: self._andaidh, 0xa5: self._andaidl, 0xa6: self._andafromidd, 0xac: self._xoraidh, 0xad: self._xoraidl, 0xae: self._xorafromidd,
            0xb4: self._oraidh, 0xb5: self._oraidl, 0xb6: self._orafromidd,
            0xbc: self._cpaidh, 0xbd: self._cpaidl, 0xbe: self._cpafromidd,
            0xe5: self._pushid, 0xe1: self._popid, 0xe9: self._jpid, 0xf9: self._ldspid, 0xe3: self._exfromspid,
            0xcb: self._idcb, 0xdd: self._opcodedd_ixy, 0xed: self._opcodeed_ixy, 0xfd: self._opcodefd_ixy
        }

        self._idcbdict: dict[int, Callable[[int], None]] = {
            0x00: self._cbrlcb, 0x01: self._cbrlcc, 0x02: self._cbrlcd, 0x03: self._cbrlce, 0x04: self._cbrlch, 0x05: self._cbrlcl, 0x06: self._cbrlcinhl, 0x07: self._cbrlca,
            0x08: self._cbrrcb, 0x09: self._cbrrcc, 0x0a: self._cbrrcd, 0x0b: self._cbrrce, 0x0c: self._cbrrch, 0x0d: self._cbrrcl, 0x0e: self._cbrrcinhl, 0x0f: self._cbrrca,
            0x10: self._cbrlb, 0x11: self._cbrlc, 0x12: self._cbrld, 0x13: self._cbrle, 0x14: self._cbrlh, 0x15: self._cbrll, 0x16: self._cbrlinhl, 0x17: self._cbrla,
            0x18: self._cbrrb, 0x19: self._cbrrc, 0x1a: self._cbrrd, 0x1b: self._cbrre, 0x1c: self._cbrrh, 0x1d: self._cbrrl, 0x1e: self._cbrrinhl, 0x1f: self._cbrra,
            0x20: self._cbslab, 0x21: self._cbslac, 0x22: self._cbslad, 0x23: self._cbslae, 0x24: self._cbslah, 0x25: self._cbslal, 0x26: self._cbslainhl, 0x27: self._cbslaa,
            0x28: self._cbsrab, 0x29: self._cbsrac, 0x2a: self._cbsrad, 0x2b: self._cbsrae, 0x2c: self._cbsrah, 0x2d: self._cbsral, 0x2e: self._cbsrainhl, 0x2f: self._cbsraa,
            0x30: self._cbslsb, 0x31: self._cbslsc, 0x32: self._cbslsd, 0x33: self._cbslse, 0x34: self._cbslsh, 0x35: self._cbslsl, 0x36: self._cbslsinhl, 0x37: self._cbslsa,
            0x38: self._cbsrlb, 0x39: self._cbsrlc, 0x3a: self._cbsrld, 0x3b: self._cbsrle, 0x3c: self._cbsrlh, 0x3d: self._cbsrll, 0x3e: self._cbsrlinhl, 0x3f: self._cbsrla,
            0x40: self._cbbit0, 0x41: self._cbbit0, 0x42: self._cbbit0, 0x43: self._cbbit0, 0x44: self._cbbit0, 0x45: self._cbbit0, 0x46: self._cbbit0, 0x47: self._cbbit0,
            0x48: self._cbbit1, 0x49: self._cbbit1, 0x4a: self._cbbit1, 0x4b: self._cbbit1, 0x4c: self._cbbit1, 0x4d: self._cbbit1, 0x4e: self._cbbit1, 0x4f: self._cbbit1,
            0x50: self._cbbit2, 0x51: self._cbbit2, 0x52: self._cbbit2, 0x53: self._cbbit2, 0x54: self._cbbit2, 0x55: self._cbbit2, 0x56: self._cbbit2, 0x57: self._cbbit2,
            0x58: self._cbbit3, 0x59: self._cbbit3, 0x5a: self._cbbit3, 0x5b: self._cbbit3, 0x5c: self._cbbit3, 0x5d: self._cbbit3, 0x5e: self._cbbit3, 0x5f: self._cbbit3,
            0x60: self._cbbit4, 0x61: self._cbbit4, 0x62: self._cbbit4, 0x63: self._cbbit4, 0x64: self._cbbit4, 0x65: self._cbbit4, 0x66: self._cbbit4, 0x67: self._cbbit4,
            0x68: self._cbbit5, 0x69: self._cbbit5, 0x6a: self._cbbit5, 0x6b: self._cbbit5, 0x6c: self._cbbit5, 0x6d: self._cbbit5, 0x6e: self._cbbit5, 0x6f: self._cbbit5,
            0x70: self._cbbit6, 0x71: self._cbbit6, 0x72: self._cbbit6, 0x73: self._cbbit6, 0x74: self._cbbit6, 0x75: self._cbbit6, 0x76: self._cbbit6, 0x77: self._cbbit6,
            0x78: self._cbbit7, 0x79: self._cbbit7, 0x7a: self._cbbit7, 0x7b: self._cbbit7, 0x7c: self._cbbit7, 0x7d: self._cbbit7, 0x7e: self._cbbit7, 0x7f: self._cbbit7,
            0x80: self._cbres0b, 0x81: self._cbres0c, 0x82: self._cbres0d, 0x83: self._cbres0e, 0x84: self._cbres0h, 0x85: self._cbres0l, 0x86: self._cbres0inhl, 0x87: self._cbres0a,
            0x88: self._cbres1b, 0x89: self._cbres1c, 0x8a: self._cbres1d, 0x8b: self._cbres1e, 0x8c: self._cbres1h, 0x8d: self._cbres1l, 0x8e: self._cbres1inhl, 0x8f: self._cbres1a,
            0x90: self._cbres2b, 0x91: self._cbres2c, 0x92: self._cbres2d, 0x93: self._cbres2e, 0x94: self._cbres2h, 0x95: self._cbres2l, 0x96: self._cbres2inhl, 0x97: self._cbres2a,
            0x98: self._cbres3b, 0x99: self._cbres3c, 0x9a: self._cbres3d, 0x9b: self._cbres3e, 0x9c: self._cbres3h, 0x9d: self._cbres3l, 0x9e: self._cbres3inhl, 0x9f: self._cbres3a,
            0xa0: self._cbres4b, 0xa1: self._cbres4c, 0xa2: self._cbres4d, 0xa3: self._cbres4e, 0xa4: self._cbres4h, 0xa5: self._cbres4l, 0xa6: self._cbres4inhl, 0xa7: self._cbres4a,
            0xa8: self._cbres5b, 0xa9: self._cbres5c, 0xaa: self._cbres5d, 0xab: self._cbres5e, 0xac: self._cbres5h, 0xad: self._cbres5l, 0xae: self._cbres5inhl, 0xaf: self._cbres5a,
            0xb0: self._cbres6b, 0xb1: self._cbres6c, 0xb2: self._cbres6d, 0xb3: self._cbres6e, 0xb4: self._cbres6h, 0xb5: self._cbres6l, 0xb6: self._cbres6inhl, 0xb7: self._cbres6a,
            0xb8: self._cbres7b, 0xb9: self._cbres7c, 0xba: self._cbres7d, 0xbb: self._cbres7e, 0xbc: self._cbres7h, 0xbd: self._cbres7l, 0xbe: self._cbres7inhl, 0xbf: self._cbres7a,
            0xc0: self._cbset0b, 0xc1: self._cbset0c, 0xc2: self._cbset0d, 0xc3: self._cbset0e, 0xc4: self._cbset0h, 0xc5: self._cbset0l, 0xc6: self._cbset0inhl, 0xc7: self._cbset0a,
            0xc8: self._cbset1b, 0xc9: self._cbset1c, 0xca: self._cbset1d, 0xcb: self._cbset1e, 0xcc: self._cbset1h, 0xcd: self._cbset1l, 0xce: self._cbset1inhl, 0xcf: self._cbset1a,
            0xd0: self._cbset2b, 0xd1: self._cbset2c, 0xd2: self._cbset2d, 0xd3: self._cbset2e, 0xd4: self._cbset2h, 0xd5: self._cbset2l, 0xd6: self._cbset2inhl, 0xd7: self._cbset2a,
            0xd8: self._cbset3b, 0xd9: self._cbset3c, 0xda: self._cbset3d, 0xdb: self._cbset3e, 0xdc: self._cbset3h, 0xdd: self._cbset3l, 0xde: self._cbset3inhl, 0xdf: self._cbset3a,
            0xe0: self._cbset4b, 0xe1: self._cbset4c, 0xe2: self._cbset4d, 0xe3: self._cbset4e, 0xe4: self._cbset4h, 0xe5: self._cbset4l, 0xe6: self._cbset4inhl, 0xe7: self._cbset4a,
            0xe8: self._cbset5b, 0xe9: self._cbset5c, 0xea: self._cbset5d, 0xeb: self._cbset5e, 0xec: self._cbset5h, 0xed: self._cbset5l, 0xee: self._cbset5inhl, 0xef: self._cbset5a,
            0xf0: self._cbset6b, 0xf1: self._cbset6c, 0xf2: self._cbset6d, 0xf3: self._cbset6e, 0xf4: self._cbset6h, 0xf5: self._cbset6l, 0xf6: self._cbset6inhl, 0xf7: self._cbset6a,
            0xf8: self._cbset7b, 0xf9: self._cbset7c, 0xfa: self._cbset7d, 0xfb: self._cbset7e, 0xfc: self._cbset7h, 0xfd: self._cbset7l, 0xfe: self._cbset7inhl, 0xff: self._cbset7a
        }

    def interruption(self) -> None:
        self._lastFlagQ = False
        self.halted = False

        self.bus_access.interrupt_handling_time(7)
        self.regR += 1
        self.ffIFF1 = self.ffIFF2 = False
        self._push(self.regPC)
        if self.modeINT == IM2:
            self.regPC = self.bus_access.peekw((self.regI << 8) | 0xff)
        else:
            self.regPC = 0x0038
        self.memptr = self.regPC

    def nmi(self) -> None:
        self._lastFlagQ = False
        self.halted = False

        self.bus_access.fetch_opcode(self.regPC)
        self.bus_access.interrupt_handling_time(1)

        self.regR += 1
        self.ffIFF1 = False
        self._push(self.regPC)
        self.regPC = self.memptr = 0x0066

    def _adjust_inxRoutxRFlags(self):
        self._sz5h3pnFlags &= ~FLAG_53_MASK
        self._sz5h3pnFlags |= (self.regPC >> 8) & FLAG_53_MASK

        pf = self._sz5h3pnFlags & PARITY_MASK
        if self.carryFlag:
            addsub = 1 - (self._sz5h3pnFlags & ADDSUB_MASK)
            pf ^= self._sz53pn_addTable[(self.regB + addsub) & 0x07] ^ PARITY_MASK
            if (self.regB & 0x0F) == (0x00 if addsub != 1 else 0x0F):
                self._sz5h3pnFlags |= HALFCARRY_MASK
            else:
                self._sz5h3pnFlags &= ~HALFCARRY_MASK
        else:
            pf ^= self._sz53pn_addTable[self.regB & 0x07] ^ PARITY_MASK
            self._sz5h3pnFlags &= ~HALFCARRY_MASK

        if (pf & PARITY_MASK) == PARITY_MASK:
            self._sz5h3pnFlags |= PARITY_MASK
        else:
            self._sz5h3pnFlags &= ~PARITY_MASK

    def execute(self, states_limit: int) -> None:
        while self.bus_access.tstates < states_limit:
            self.execute_one_cycle()

    def execute_one_cycle(self) -> None:
        if self.show_debug_info:
            self.show_registers()

        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regR += 1

        # if self.prefixOpcode == 0 && breakpointAt.get(regPC):
        #     opCode = NotifyImpl.breakpoint(regPC, opCode);

        if not self.halted:
            self.regPC = (self.regPC + 1) & 0xffff

            if self._prefixOpcode == 0x00:
                self._flagQ = self.pendingEI = False
                self._main_cmds[opcode]()
            elif self._prefixOpcode == 0xDD:
                self._prefixOpcode = 0

                code = self._ixiydict.get(opcode)
                if code is None:
                    self._main_cmds[opcode]()
                else:
                    self.regIX = code(self.regIX)

            elif self._prefixOpcode == 0xED:
                self._prefixOpcode = 0
                code = self._eddict.get(opcode)
                if code is not None:
                    code()
            elif self._prefixOpcode == 0xFD:
                self._prefixOpcode = 0

                code = self._ixiydict.get(opcode)
                if code is None:
                    self._main_cmds[opcode]()
                else:
                    self.regIY = code(self.regIY)
            else:
                pass
                # log.error(String.format("ERROR!: prefixOpcode = %02x, opCode = %02x", prefixOpcode, opCode));

            if self._prefixOpcode != 0x00:
                return

            self._lastFlagQ = self._flagQ

            # if execDone:
            #     NotifyImpl.execDone();

        if self.activeNMI:
            self.activeNMI = False
            self.nmi()
            return

        if self.ffIFF1 and not self.pendingEI and self.bus_access.is_active_INT():
            self.interruption()

        # if not self.ffIFF1 and not self.pendingEI and self.bus_access.is_active_INT():
        #     self.show_debug_info = True

    def show_registers(self):
        print(
              # f"t: {self.bus_access.tstates:06} "
              f"PC: 0x{self.regPC:04x} "
              f"SP: 0x{self.regSP:04x} "
              f"OPCODE: {self.memory.peekb(self.regPC):02x}({self.memory.peekb(self.regPC):03d}) "
              f"A:0x{self.regA:02x} "
              f"HL:0x{self.get_reg_HL():04x} "
              f"BC:0x{self.get_reg_BC():04x} "
              f"DE:0x{self.get_reg_DE():04x} "
              f"F:0x{self.get_flags():02x} "
              f"C:{(1 if self.carryFlag else 0)} "
              f"N:{1 if self.is_add_sub_flag() else 0} "
              f"PV:{1 if self.is_par_over_flag() else 0} "
              f"3:{1 if self.is_bit3_flag() else 0} "
              f"H:{1 if self.is_half_carry_flag() else 0} "
              f"5:{1 if self.is_bit5_flag() else 0} "
              f"Z:{1 if self.is_zero_flag() else 0} "
              f"S:{1 if self.is_sign_flag() else 0} "
              f"IFF1:{1 if self.ffIFF1 else 0} "
              f"IFF2:{1 if self.ffIFF2 else 0} "
              f"Mem: 0x{self.regPC:04x}: "
              f"{self.memory.peekb(self.regPC):02x}, "
              f"{self.memory.peekb(self.regPC + 1):02x}, "
              f"{self.memory.peekb(self.regPC + 2):02x}, "
              f"{self.memory.peekb(self.regPC + 3):02x}, "
              f"{self.memory.peekb(self.regPC + 4):02x}, "
              f"{self.memory.peekb(self.regPC + 5):02x}, "
              f"{self.memory.peekb(self.regPC + 6):02x}, "
              f"{self.memory.peekb(self.regPC + 7):02x}")

    def reset(self) -> None:
        if self.pinReset:
            self.pinReset = False
        else:
            self.regA = self.regAx = 0xff
            self.set_flags(0xff)
            self.regFx = 0xff
            self.regB = self.regBx = 0xff
            self.regC = self.regCx = 0xff
            self.regD = self.regDx = 0xff
            self.regE = self.regEx = 0xff
            self.regH = self.regHx = 0xff
            self.regL = self.regLx = 0xff

            self.regIX = self.regIY = 0xffff

            self.regSP = 0xffff

            self.memptr = 0xffff

        self.regPC = 0
        self.regI = self.regR = 0
        self.regRbit7 = False
        self.ffIFF1 = False
        self.ffIFF2 = False
        self.pendingEI = False
        self.activeNMI = False
        self.activeINT = False
        self.halted = False
        self.modeINT = IM0
        self._lastFlagQ = False
        self._prefixOpcode = 0x00

    def set_reg_A(self, value: int) -> None:
        self.regA = value & 0xff

    def set_reg_B(self, value: int) -> None:
        self.regB = value & 0xff

    def set_reg_C(self, value: int) -> None:
        self.regC = value & 0xff

    def set_reg_D(self, value: int) -> None:
        self.regD = value & 0xff

    def set_reg_E(self, value: int) -> None:
        self.regE = value & 0xff

    def set_reg_H(self, value: int) -> None:
        self.regH = value & 0xff

    def set_reg_L(self, value: int) -> None:
        self.regL = value & 0xff

    def set_reg_Ax(self, value: int) -> None:
        self.regAx = value & 0xff

    def set_reg_Fx(self, value: int) -> None:
        self.regFx = value & 0xff

    def set_reg_Bx(self, value: int) -> None:
        self.regBx = value & 0xff

    def set_reg_Cx(self, value: int) -> None:
        self.regCx = value & 0xff

    def set_reg_Dx(self, value: int) -> None:
        self.regDx = value & 0xff

    def set_reg_Ex(self, value: int) -> None:
        self.regEx = value & 0xff

    def set_reg_Hx(self, value: int) -> None:
        self.regHx = value & 0xff

    def set_reg_Lx(self, value: int) -> None:
        self.regLx = value & 0xff

    def get_reg_AF(self) -> int:
        return (self.regA << 8) | (self._sz5h3pnFlags | CARRY_MASK if self.carryFlag else self._sz5h3pnFlags)

    def set_reg_AF(self, word: int) -> None:
        self.regA = (word >> 8) & 0xff

        self._sz5h3pnFlags = word & 0xfe
        self.carryFlag = (word & CARRY_MASK) != 0

    def get_reg_AFx(self) -> int: return (self.regAx << 8) | self.regFx

    def set_reg_AFx(self, word: int) -> None:
        self.regAx = (word >> 8) & 0xff
        self.regFx = word & 0xff

    def get_reg_BC(self) -> int: return (self.regB << 8) | self.regC

    def set_reg_BC(self, word: int) -> None:
        self.regB = (word >> 8) & 0xff
        self.regC = word & 0xff

    def _inc_reg_BC(self) -> None:
        self.regC += 1
        if self.regC < 0x100: return

        self.regC = 0
        self.regB += 1
        if self.regB < 0x100: return

        self.regB = 0

    def _dec_reg_BC(self) -> None:
        self.regC -= 1
        if self.regC >= 0: return

        self.regC = 0xff

        self.regB -= 1
        if self.regB >= 0: return

        self.regB = 0xff

    def get_reg_BCx(self) -> int: return (self.regBx << 8) | self.regCx

    def set_reg_BCx(self, word: int) -> None:
        self.regBx = (word >> 8) & 0xff
        self.regCx = word & 0xff

    def get_reg_DE(self) -> int: return (self.regD << 8) | self.regE

    def set_reg_DE(self, word: int) -> None:
        self.regD = (word >> 8) & 0xff
        self.regE = word & 0xff

    def _inc_reg_DE(self) -> None:
        self.regE += 1
        if self.regE < 0x100: return

        self.regE = 0
        self.regD += 1
        if self.regD < 0x100: return

        self.regD = 0

    def _dec_reg_DE(self) -> None:
        self.regE -= 1
        if self.regE >= 0: return

        self.regE = 0xff
        self.regD -= 1
        if self.regD >= 0: return

        self.regD = 0xff

    def get_reg_DEx(self) -> int: return (self.regDx << 8) | self.regEx

    def set_reg_DEx(self, word: int) -> None:
        self.regDx = (word >> 8) & 0xff
        self.regEx = word & 0xff

    def get_reg_HL(self) -> int: return (self.regH << 8) | self.regL

    def set_reg_HL(self, word: int) -> None:
        self.regH = (word >> 8) & 0xff
        self.regL = word & 0xff

    def _inc_reg_HL(self) -> None:
        self.regL += 1
        if self.regL < 0x100: return
        self.regL = 0

        self.regH += 1
        if self.regH < 0x100: return
        self.regH = 0

    def _dec_reg_HL(self) -> None:
        self.regL -= 1
        if self.regL >= 0: return
        self.regL = 0xff

        self.regH -= 1
        if self.regH >= 0: return
        self.regH = 0xff

    def get_reg_HLx(self) -> int: return (self.regHx << 8) | self.regLx

    def set_reg_HLx(self, word: int) -> None:
        self.regHx = (word >> 8) & 0xff
        self.regLx = word & 0xff

    def set_reg_PC(self, address: int) -> None:
        self.regPC = address & 0xffff

    def set_reg_SP(self, word: int) -> None:
        self.regSP = word & 0xffff

    def set_reg_IX(self, word: int) -> None:
        self.regIX = word & 0xffff

    def set_reg_IY(self, word) -> None:
        self.regIY = word & 0xffff

    def set_reg_I(self, value: int) -> None:
        self.regI = value & 0xff

    def get_reg_R(self) -> int:
        return (self.regR & 0x7f) | SIGN_MASK if self.regRbit7 else self.regR & 0x7f

    def set_reg_R(self, value: int) -> None:
        self.regR = value & 0x7f
        self.regRbit7 = value > 0x7f

    def get_pair_IR(self) -> int:
        if self.regRbit7:
            return (self.regI << 8) | ((self.regR & 0x7f) | SIGN_MASK)
        return (self.regI << 8) | (self.regR & 0x7f)

    def get_mem_ptr(self) -> int:
        return self.memptr & 0xffff

    def set_mem_ptr(self, word) -> None:
        self.memptr = word & 0xffff

    def is_add_sub_flag(self) -> bool: return (self._sz5h3pnFlags & ADDSUB_MASK) != 0

    def set_add_sub_flag(self, state: bool) -> None:
        if state:
            self._sz5h3pnFlags |= ADDSUB_MASK
        else:
            self._sz5h3pnFlags &= ~ADDSUB_MASK

    def is_par_over_flag(self) -> bool: return (self._sz5h3pnFlags & PARITY_MASK) != 0

    def set_par_over_flag(self, state: bool) -> None:
        if state:
            self._sz5h3pnFlags |= PARITY_MASK
        else:
            self._sz5h3pnFlags &= ~PARITY_MASK

    def is_bit3_flag(self) -> bool: return (self._sz5h3pnFlags & BIT3_MASK) != 0

    def set_bit3_fag(self, state: int) -> None:
        if state:
            self._sz5h3pnFlags |= BIT3_MASK
        else:
            self._sz5h3pnFlags &= ~BIT3_MASK

    def is_half_carry_flag(self): return (self._sz5h3pnFlags & HALFCARRY_MASK) != 0

    def set_half_carry_flag(self, state: bool) -> None:
        if state:
            self._sz5h3pnFlags |= HALFCARRY_MASK
        else:
            self._sz5h3pnFlags &= ~HALFCARRY_MASK

    def is_bit5_flag(self) -> bool: return (self._sz5h3pnFlags & BIT5_MASK) != 0

    def set_bit5_flag(self, state: bool) -> None:
        if state:
            self._sz5h3pnFlags |= BIT5_MASK
        else:
            self._sz5h3pnFlags &= ~BIT5_MASK

    def is_zero_flag(self) -> bool: return (self._sz5h3pnFlags & ZERO_MASK) != 0

    def set_zero_flag(self, state: bool) -> None:
        if state:
            self._sz5h3pnFlags |= ZERO_MASK
        else:
            self._sz5h3pnFlags &= ~ZERO_MASK

    def is_sign_flag(self) -> bool: return self._sz5h3pnFlags >= SIGN_MASK

    def set_sign_flag(self, state) -> None:
        if state:
            self._sz5h3pnFlags |= SIGN_MASK
        else:
            self._sz5h3pnFlags &= ~SIGN_MASK

    def get_flags(self) -> int: return self._sz5h3pnFlags | CARRY_MASK if self.carryFlag else self._sz5h3pnFlags

    def set_flags(self, regF: int) -> None:
        self._sz5h3pnFlags = regF & 0xfe
        self.carryFlag = (regF & CARRY_MASK) != 0

    def trigger_NMI(self) -> None:
        self.activeNMI = True

    def _rlc(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        if self.carryFlag:
            oper8 |= CARRY_MASK

        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _rl(self, oper8: int) -> int:
        carry = self.carryFlag
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        if carry:
            oper8 |= CARRY_MASK

        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _sla(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _sll(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = ((oper8 << 1) | CARRY_MASK) & 0xff
        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _rrc(self, oper8: int) -> int:
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1  # >>>=
        if self.carryFlag:
            oper8 |= SIGN_MASK

        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _rr(self, oper8) -> int:
        carry = self.carryFlag
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1
        if carry:
            oper8 |= SIGN_MASK

        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _rrd(self) -> None:
        aux = (self.regA & 0x0f) << 4
        self.memptr = self.get_reg_HL()
        memHL = self.bus_access.peekb(self.memptr)
        self.regA = (self.regA & 0xf0) | (memHL & 0x0f)
        self.bus_access.address_on_bus(self.memptr, 4)
        self.bus_access.pokeb(self.memptr, (memHL >> 4) | aux)
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA]
        self.memptr += 1
        self._flagQ = True

    def _rld(self) -> None:
        aux = self.regA & 0x0f
        self.memptr = self.get_reg_HL()
        memHL = self.bus_access.peekb(self.memptr)
        self.regA = (self.regA & 0xf0) | (memHL >> 4)
        self.bus_access.address_on_bus(self.memptr, 4)
        self.bus_access.pokeb(self.memptr, ((memHL << 4) | aux) & 0xff)
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA]
        self.memptr += 1
        self._flagQ = True

    def _sra(self, oper8: int) -> int:
        sign = oper8 & SIGN_MASK
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 = (oper8 >> 1) | sign
        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _srl(self, oper8: int) -> int:
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1
        self._sz5h3pnFlags = self._sz53pn_addTable[oper8]
        self._flagQ = True
        return oper8

    def _inc8(self, oper8: int) -> int:
        oper8 = (oper8 + 1) & 0xff

        self._sz5h3pnFlags = self._sz53n_addTable[oper8]

        if (oper8 & 0x0f) == 0:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if oper8 == 0x80:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self._flagQ = True
        return oper8

    def _dec8(self, oper8: int) -> int:
        oper8 = (oper8 - 1) & 0xff

        self._sz5h3pnFlags = self._sz53n_subTable[oper8]

        if (oper8 & 0x0f) == 0x0f:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if oper8 == 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self._flagQ = True
        return oper8

    def _add(self, oper8: int) -> None:
        res = self.regA + oper8

        self.carryFlag = res > 0xff
        res &= 0xff
        self._sz5h3pnFlags = self._sz53n_addTable[res]

        if (res & 0x0f) < (self.regA & 0x0f):
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ ~oper8) & (self.regA ^ res)) > 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self._flagQ = True

    def _adc(self, oper8: int) -> None:
        res = self.regA + oper8

        if self.carryFlag:
            res += 1

        self.carryFlag = res > 0xff
        res &= 0xff
        self._sz5h3pnFlags = self._sz53n_addTable[res]

        if ((self.regA ^ oper8 ^ res) & 0x10) != 0:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ ~oper8) & (self.regA ^ res)) > 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self._flagQ = True

    def _add16(self, reg16: int, oper16: int) -> int:
        oper16 += reg16

        self.carryFlag = oper16 > 0xffff
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | ((oper16 >> 8) & FLAG_53_MASK)
        oper16 &= 0xffff

        if (oper16 & 0x0fff) < (reg16 & 0x0fff):
            self._sz5h3pnFlags |= HALFCARRY_MASK

        self.memptr = reg16 + 1
        self._flagQ = True
        return oper16

    def _adc16(self, reg16: int) -> None:
        regHL = self.get_reg_HL()
        self.memptr = regHL + 1

        res = regHL + reg16
        if self.carryFlag:
            res += 1

        self.carryFlag = res > 0xffff
        res &= 0xffff
        self.set_reg_HL(res)

        self._sz5h3pnFlags = self._sz53n_addTable[self.regH]
        if res != 0:
            self._sz5h3pnFlags &= ~ZERO_MASK

        if ((res ^ regHL ^ reg16) & 0x1000) != 0:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((regHL ^ ~reg16) & (regHL ^ res)) > 0x7fff:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self._flagQ = True

    def _sub(self, oper8: int) -> None:
        res = self.regA - oper8

        self.carryFlag = res < 0
        res &= 0xff
        self._sz5h3pnFlags = self._sz53n_subTable[res]

        if (res & 0x0f) > (self.regA & 0x0f):
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self._flagQ = True

    def _sbc(self, oper8: int) -> None:
        res = self.regA - oper8

        if self.carryFlag:
            res -= 1

        self.carryFlag = res < 0
        res &= 0xff
        self._sz5h3pnFlags = self._sz53n_subTable[res]

        if ((self.regA ^ oper8 ^ res) & 0x10) != 0:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self._flagQ = True

    def _sbc16(self, reg16: int) -> None:
        regHL = self.get_reg_HL()
        self.memptr = regHL + 1

        res = regHL - reg16
        if self.carryFlag:
            res -= 1

        self.carryFlag = res < 0
        res &= 0xffff
        self.set_reg_HL(res)

        self._sz5h3pnFlags = self._sz53n_subTable[self.regH]
        if res != 0:
            self._sz5h3pnFlags &= ~ZERO_MASK

        if ((res ^ regHL ^ reg16) & 0x1000) != 0:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((regHL ^ reg16) & (regHL ^ res)) > 0x7fff:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self._flagQ = True

    def _and(self, oper8: int) -> None:
        self.regA &= oper8
        self.carryFlag = False
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA] | HALFCARRY_MASK
        self._flagQ = True

    def _xor(self, oper8: int) -> None:
        self.regA = (self.regA ^ oper8) & 0xff
        self.carryFlag = False
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA]
        self._flagQ = True

    def _or(self, oper8: int) -> None:
        self.regA = (self.regA | oper8) & 0xff
        self.carryFlag = False
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA]
        self._flagQ = True

    def _cp(self, oper8: int) -> None:
        res = self.regA - (oper8 & 0xff)

        self.carryFlag = res < 0
        res &= 0xff

        self._sz5h3pnFlags = (self._sz53n_addTable[oper8] & FLAG_53_MASK) | (self._sz53n_subTable[res] & FLAG_SZHN_MASK)

        if (res & 0x0f) > (self.regA & 0x0f):
            self._sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self._sz5h3pnFlags |= OVERFLOW_MASK

        self._flagQ = True

    def _daa(self) -> None:
        suma = 0
        carry = self.carryFlag

        if (self._sz5h3pnFlags & HALFCARRY_MASK) != 0 or (self.regA & 0x0f) > 0x09:
            suma = 6

        if carry or (self.regA > 0x99):
            suma |= 0x60

        if self.regA > 0x99:
            carry = True

        if (self._sz5h3pnFlags & ADDSUB_MASK) != 0:
            self._sub(suma)
            self._sz5h3pnFlags = (self._sz5h3pnFlags & HALFCARRY_MASK) | self._sz53pn_subTable[self.regA]
        else:
            self._add(suma)
            self._sz5h3pnFlags = (self._sz5h3pnFlags & HALFCARRY_MASK) | self._sz53pn_addTable[self.regA]

        self.carryFlag = carry
        self._flagQ = True

    def _pop(self) -> int:
        word = self.bus_access.peekw(self.regSP)
        self.regSP = (self.regSP + 2) & 0xffff
        return word

    def _push(self, word) -> None:
        self.regSP = (self.regSP - 1) & 0xffff
        self.bus_access.pokeb(self.regSP, word >> 8)
        self.regSP = (self.regSP - 1) & 0xffff
        self.bus_access.pokeb(self.regSP, word)

    def _ldi(self) -> None:
        work8 = self.bus_access.peekb(self.get_reg_HL())

        regDE = self.get_reg_DE()
        self.bus_access.pokeb(regDE, work8)
        self.bus_access.address_on_bus(regDE, 2)
        self._inc_reg_HL()
        self._inc_reg_DE()
        self._dec_reg_BC()
        work8 += self.regA

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZ_MASK) | (work8 & BIT3_MASK)

        if (work8 & ADDSUB_MASK) != 0:
            self._sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self._sz5h3pnFlags |= PARITY_MASK

        self._flagQ = True

    def _ldd(self) -> None:
        work8 = self.bus_access.peekb(self.get_reg_HL())

        regDE = self.get_reg_DE()
        self.bus_access.pokeb(regDE, work8)
        self.bus_access.address_on_bus(regDE, 2)
        self._dec_reg_HL()
        self._dec_reg_DE()
        self._dec_reg_BC()
        work8 += self.regA

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZ_MASK) | (work8 & BIT3_MASK)

        if (work8 & ADDSUB_MASK) != 0:
            self._sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self._sz5h3pnFlags |= PARITY_MASK

        self._flagQ = True

    def _cpi(self) -> None:
        regHL = self.get_reg_HL()
        memHL = self.bus_access.peekb(regHL)
        carry = self.carryFlag
        self._cp(memHL)
        self.carryFlag = carry
        self.bus_access.address_on_bus(regHL, 5)
        self._inc_reg_HL()
        self._dec_reg_BC()

        memHL = self.regA - memHL - (1 if (self._sz5h3pnFlags & HALFCARRY_MASK) != 0 else 0)
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHN_MASK) | (memHL & BIT3_MASK)

        if (memHL & ADDSUB_MASK) != 0:
            self._sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self._sz5h3pnFlags |= PARITY_MASK

        self.memptr += 1
        self._flagQ = True

    def _cpd(self) -> None:
        regHL = self.get_reg_HL()
        memHL = self.bus_access.peekb(regHL)
        carry = self.carryFlag
        self._cp(memHL)
        self.carryFlag = carry
        self.bus_access.address_on_bus(regHL, 5)
        self._dec_reg_HL()
        self._dec_reg_BC()
        memHL = self.regA - memHL - (1 if (self._sz5h3pnFlags & HALFCARRY_MASK) != 0 else 0)
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHN_MASK) | (memHL & BIT3_MASK)

        if (memHL & ADDSUB_MASK) != 0:
            self._sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self._sz5h3pnFlags |= PARITY_MASK

        self.memptr -= 1
        self._flagQ = True

    def _ini(self) -> None:
        self.memptr = self.get_reg_BC()
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        work8 = self.bus_access.in_port(self.memptr)
        self.bus_access.pokeb(self.get_reg_HL(), work8)

        self.memptr += 1
        self.regB = (self.regB - 1) & 0xff

        self._inc_reg_HL()

        self._sz5h3pnFlags = self._sz53pn_addTable[self.regB]
        if work8 > 0x7f:
            self._sz5h3pnFlags |= ADDSUB_MASK

        self.carryFlag = False
        tmp = work8 + ((self.regC + 1) & 0xff)
        if tmp > 0xff:
            self._sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self._sz53pn_addTable[((tmp & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self._sz5h3pnFlags |= PARITY_MASK
        else:
            self._sz5h3pnFlags &= ~PARITY_MASK

        self._flagQ = True

    def _ind(self) -> None:
        self.memptr = self.get_reg_BC()
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        work8 = self.bus_access.in_port(self.memptr)
        self.bus_access.pokeb(self.get_reg_HL(), work8)

        self.memptr -= 1
        self.regB = (self.regB - 1) & 0xff

        self._dec_reg_HL()

        self._sz5h3pnFlags = self._sz53pn_addTable[self.regB]
        if work8 > 0x7f:
            self._sz5h3pnFlags |= ADDSUB_MASK

        self.carryFlag = False

        tmp = work8 + ((self.regC - 1) & 0xff)
        if tmp > 0xff:
            self._sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self._sz53pn_addTable[((tmp & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self._sz5h3pnFlags |= PARITY_MASK
        else:
            self._sz5h3pnFlags &= ~PARITY_MASK

        self._flagQ = True

    def _outi(self) -> None:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        self.regB = (self.regB - 1) & 0xff
        self.memptr = self.get_reg_BC()

        work8 = self.bus_access.peekb(self.get_reg_HL())
        self.bus_access.out_port(self.memptr, work8)
        self.memptr += 1

        self._inc_reg_HL()

        self.carryFlag = False
        if work8 > 0x7f:
            self._sz5h3pnFlags = self._sz53n_subTable[self.regB]
        else:
            self._sz5h3pnFlags = self._sz53n_addTable[self.regB]

        if (self.regL + work8) > 0xff:
            self._sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self._sz53pn_addTable[(((self.regL + work8) & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self._sz5h3pnFlags |= PARITY_MASK

        self._flagQ = True

    def _outd(self) -> None:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        self.regB = (self.regB - 1) & 0xff
        self.memptr = self.get_reg_BC()

        work8 = self.bus_access.peekb(self.get_reg_HL())
        self.bus_access.out_port(self.memptr, work8)
        self.memptr -= 1

        self._dec_reg_HL()

        self.carryFlag = False
        if work8 > 0x7f:
            self._sz5h3pnFlags = self._sz53n_subTable[self.regB]
        else:
            self._sz5h3pnFlags = self._sz53n_addTable[self.regB]

        if (self.regL + work8) > 0xff:
            self._sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self._sz53pn_addTable[(((self.regL + work8) & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self._sz5h3pnFlags |= PARITY_MASK

        self._flagQ = True

    def _bit(self, mask: int, reg: int) -> None:
        zero_flag = (mask & reg) == 0

        self._sz5h3pnFlags = (self._sz53n_addTable[reg] & ~FLAG_SZP_MASK) | HALFCARRY_MASK

        if zero_flag:
            self._sz5h3pnFlags |= (PARITY_MASK | ZERO_MASK)

        if mask == SIGN_MASK and not zero_flag:
            self._sz5h3pnFlags |= SIGN_MASK

        self._flagQ = True

    @staticmethod
    def _nop():
        pass
    
    # EXX
    def _exx(self):
        work8 = self.regB
        self.regB = self.regBx
        self.regBx = work8

        work8 = self.regC
        self.regC = self.regCx
        self.regCx = work8

        work8 = self.regD
        self.regD = self.regDx
        self.regDx = work8

        work8 = self.regE
        self.regE = self.regEx
        self.regEx = work8

        work8 = self.regH
        self.regH = self.regHx
        self.regHx = work8

        work8 = self.regL
        self.regL = self.regLx
        self.regLx = work8

    # EX AF,AF'
    def _ex_af_af(self):
        work8 = self.regA
        self.regA = self.regAx
        self.regAx = work8

        work8 = self.get_flags()
        self.set_flags(self.regFx)
        self.regFx = work8

    def _djnz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        offset = self.bus_access.peeksb(self.regPC)
        self.regB -= 1
        if self.regB != 0:
            self.regB &= 0xff
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC = self.memptr = ((self.regPC + offset + 1) & 0xffff)
        else:
            self.regPC = (self.regPC + 1) & 0xffff
    
    def _jr(self):
        offset = self.bus_access.peeksb(self.regPC)
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regPC = self.memptr = (self.regPC + offset + 1) & 0xffff
    
    def _jrnz(self):
        offset = self.bus_access.peeksb(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def _jrz(self):
        offset = self.bus_access.peeksb(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) != 0:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def _jrnc(self):
        offset = self.bus_access.peeksb(self.regPC)
        if not self.carryFlag:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def _jrc(self):
        offset = self.bus_access.peeksb(self.regPC)
        if self.carryFlag:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    # LD self.rr,nn / ADD HL,self.rr
    def _ldbcnn(self):
        self.set_reg_BC(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff

    def _addhlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.set_reg_HL(self._add16(self.get_reg_HL(), self.get_reg_BC()))

    def _lddenn(self):
        self.set_reg_DE(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _addhlde(self):
        self.set_reg_HL(self._add16(self.get_reg_HL(), self.get_reg_DE()))

    def _ldhlnn(self):
        self.set_reg_HL(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _addhlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        work16 = self.get_reg_HL()
        self.set_reg_HL(self._add16(work16, work16))
    
    def _ldspnn(self):
        self.regSP = self.bus_access.peekw(self.regPC)
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _addhlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.set_reg_HL(self._add16(self.get_reg_HL(), self.regSP))
    
    # LD (**),A/A,(**)
    def _ldtobca(self):
        self.bus_access.pokeb(self.get_reg_BC(), self.regA)
        self.memptr = self.regA << 8 + (self.regC & 0xff)

    def _ldafrombc(self):
        self.memptr = self.get_reg_BC()
        self.regA = self.bus_access.peekb(self.memptr)
        self.memptr += 1

    def _ldtodea(self):
        self.bus_access.pokeb(self.get_reg_DE(), self.regA)
        self.memptr = (self.regA << 8) | ((self.regE + 1) & 0xff)
    
    def _ldafromde(self):
        self.memptr = self.get_reg_DE()
        self.regA = self.bus_access.peekb(self.get_reg_DE())
        self.memptr += 1

    def _ldtonnhl(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_HL())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _ldhlfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_HL(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _ldtonna(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokeb(self.memptr, self.regA)
        self.memptr = (self.regA << 8) | ((self.memptr + 1) & 0xff)
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _ldafromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.regA = self.bus_access.peekb(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    # INC/DEC *
    def _incbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._inc_reg_BC()

    def _decbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._dec_reg_BC()

    def _incde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._inc_reg_DE()
    
    def _decde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._dec_reg_DE()

    def _inchl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._inc_reg_HL()

    def _dechl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self._dec_reg_HL()
    
    def _incsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = (self.regSP + 1) & 0xffff
    
    def _decsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = (self.regSP - 1) & 0xffff
    
    # INC *
    def _incb(self):
        self.regB = self._inc8(self.regB)

    def _incc(self):
        self.regC = self._inc8(self.regC)

    def _incd(self):
        self.regD = self._inc8(self.regD)
    
    def _ince(self):
        self.regE = self._inc8(self.regE)

    def _inch(self):
        self.regH = self._inc8(self.regH)

    def _incl(self):
        self.regL = self._inc8(self.regL)

    def _incinhl(self):
        work16 = self.get_reg_HL()
        work8 = self._inc8(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _inca(self):
        self.regA = self._inc8(self.regA)
    
    # DEC *
    def _decb(self):
        self.regB = self._dec8(self.regB)

    def _decc(self):
        self.regC = self._dec8(self.regC)

    def _decd(self):
        self.regD = self._dec8(self.regD)
    
    def _dece(self):
        self.regE = self._dec8(self.regE)

    def _dech(self):
        self.regH = self._dec8(self.regH)

    def _decl(self):
        self.regL = self._dec8(self.regL)

    def _decinhl(self):
        work16 = self.get_reg_HL()
        work8 = self._dec8(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _deca(self):
        self.regA = self._dec8(self.regA)

    # LD *,N
    def _ldbn(self):
        self.regB = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff

    def _ldcn(self):
        self.regC = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff

    def _lddn(self):
        self.regD = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _lden(self):
        self.regE = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _ldhn(self):
        self.regH = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _ldln(self):
        self.regL = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _ldtohln(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _ldan(self):
        self.regA = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    # R**A
    def _rlca(self):
        self.carryFlag = self.regA > 0x7f
        self.regA = (self.regA << 1) & 0xff
        if self.carryFlag:
            self.regA |= CARRY_MASK

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self._flagQ = True

    # Rotate Left through Carry - alters H N C 3 5 flags (CHECKED)
    def _rla(self):
        oldCarry = self.carryFlag
        self.carryFlag = (self.regA > 0x7f)
        self.regA = (self.regA << 1) & 0xff
        if oldCarry:
            self.regA |= CARRY_MASK

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self._flagQ = True
    
    # Rotate Right - alters H N C 3 5 flags (CHECKED)
    def _rrca(self):
        self.carryFlag = (self.regA & CARRY_MASK) != 0
        self.regA >>= 1
        if self.carryFlag:
            self.regA |= SIGN_MASK

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self._flagQ = True

    # Rotate Right through Carry - alters H N C 3 5 flags (CHECKED)
    def _rra(self):
        oldCarry = self.carryFlag
        self.carryFlag = (self.regA & CARRY_MASK) != 0
        self.regA >>= 1
        if oldCarry:
            self.regA |= SIGN_MASK

        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self._flagQ = True

    # One's complement - alters N H 3 5 flags (CHECKED)
    def _cpla(self):
        self.regA ^= 0xff
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | HALFCARRY_MASK | (self.regA & FLAG_53_MASK) | ADDSUB_MASK

        self._flagQ = True
    
    # self.set carry flag - alters N H 3 5 C flags (CHECKED)
    def _scf(self):
        regQ = self._sz5h3pnFlags if self._lastFlagQ else 0
        self.carryFlag = True
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (((regQ ^ self._sz5h3pnFlags) | self.regA) & FLAG_53_MASK)
        self._flagQ = True
    
    # Complement carry flag - alters N 3 5 C flags (CHECKED)
    def _ccf(self):
        regQ = self._sz5h3pnFlags if self._lastFlagQ else 0
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZP_MASK) | (((regQ ^ self._sz5h3pnFlags) | self.regA) & FLAG_53_MASK)
        if self.carryFlag:
            self._sz5h3pnFlags |= HALFCARRY_MASK

        self.carryFlag = not self.carryFlag
        self._flagQ = True
    
    # LD B,*
    @staticmethod
    def _ldbb():
        pass
    
    def _ldbc(self):
        self.regB = self.regC

    def _ldbd(self):
        self.regB = self.regD

    def _ldbe(self):
        self.regB = self.regE

    def _ldbh(self):
        self.regB = self.regH

    def _ldbl(self):
        self.regB = self.regL

    def _ldbfromhl(self):
        self.regB = self.bus_access.peekb(self.get_reg_HL())

    def _ldba(self):
        self.regB = self.regA

    # LD C,*
    def _ldcb(self):
        self.regC = self.regB

    @staticmethod
    def _ldcc():
        pass

    def _ldcd(self):
        self.regC = self.regD

    def _ldce(self):
        self.regC = self.regE

    def _ldch(self):
        self.regC = self.regH

    def _ldcl(self):
        self.regC = self.regL

    def _ldcfromhl(self):
        self.regC = self.bus_access.peekb(self.get_reg_HL())

    def _ldca(self):
        self.regC = self.regA

    # LD D,*
    def _lddb(self):
        self.regD = self.regB

    def _lddc(self):
        self.regD = self.regC

    @staticmethod
    def _lddd():
        pass

    def _ldde(self):
        self.regD = self.regE

    def _lddh(self):
        self.regD = self.regH

    def _lddl(self):
        self.regD = self.regL

    def _lddfromhl(self):
        self.regD = self.bus_access.peekb(self.get_reg_HL())

    def _ldda(self):
        self.regD = self.regA

    # LD E,*
    def _ldeb(self):
        self.regE = self.regB

    def _ldec(self):
        self.regE = self.regC

    def _lded(self):
        self.regE = self.regD

    @staticmethod
    def _ldee():
        pass
    
    def _ldeh(self):
        self.regE = self.regH

    def _ldel(self):
        self.regE = self.regL

    def _ldefromhl(self):
        self.regE = self.bus_access.peekb(self.get_reg_HL())

    def _ldea(self):
        self.regE = self.regA

    # LD H,*
    def _ldhb(self):
        self.regH = self.regB

    def _ldhc(self):
        self.regH = self.regC

    def _ldhd(self):
        self.regH = self.regD

    def _ldhe(self):
        self.regH = self.regE

    @staticmethod
    def _ldhh():
        pass
    
    def _ldhl(self):
        self.regH = self.regL

    def _ldhfromhl(self):
        self.regH = self.bus_access.peekb(self.get_reg_HL())

    def _ldha(self):
        self.regH = self.regA

    # LD L,*
    def _ldlb(self):
        self.regL = self.regB

    def _ldlc(self):
        self.regL = self.regC

    def _ldld(self):
        self.regL = self.regD

    def _ldle(self):
        self.regL = self.regE

    def _ldlh(self):
        self.regL = self.regH

    @staticmethod
    def _ldll():
        pass
    
    def _ldlfromhl(self):
        self.regL = self.bus_access.peekb(self.get_reg_HL())

    def _ldla(self):
        self.regL = self.regA

    # LD (HL),*
    def _ldtohlb(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regB)

    def _ldtohlc(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regC)

    def _ldtohld(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regD)

    def _ldtohle(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regE)

    def _ldtohlh(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regH)

    def _ldtohll(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regL)

    def _ldtohla(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regA)

    def _halt(self):
        self.halted = True

    # LD A,*
    def _ldab(self):
        self.regA = self.regB

    def _ldac(self):
        self.regA = self.regC

    def _ldad(self):
        self.regA = self.regD

    def _ldae(self):
        self.regA = self.regE

    def _ldah(self):
        self.regA = self.regH

    def _ldal(self):
        self.regA = self.regL

    def _ldafromhl(self):
        self.regA = self.bus_access.peekb(self.get_reg_HL())

    @staticmethod
    def _ldaa():
        pass
    
    # ADD A,*
    def _addab(self):
        self._add(self.regB)

    def _addac(self):
        self._add(self.regC)

    def _addad(self):
        self._add(self.regD)

    def _addae(self):
        self._add(self.regE)

    def _addah(self):
        self._add(self.regH)
    
    def _addal(self):
        self._add(self.regL)
    
    def _addafromhl(self):
        self._add(self.bus_access.peekb(self.get_reg_HL()))
    
    def _addaa(self):
        self._add(self.regA)
    
    # ADC A,*
    def _adcab(self):
        self._adc(self.regB)
    
    def _adcac(self):
        self._adc(self.regC)
    
    def _adcad(self):
        self._adc(self.regD)
    
    def _adcae(self):
        self._adc(self.regE)
    
    def _adcah(self):
        self._adc(self.regH)
        return 4
    
    def _adcal(self):
        self._adc(self.regL)
    
    def _adcafromhl(self):
        self._adc(self.bus_access.peekb(self.get_reg_HL()))
    
    def _adcaa(self):
        self._adc(self.regA)
    
    # SUB A,*
    def _subab(self):
        self._sub(self.regB)
    
    def _subac(self):
        self._sub(self.regC)
        return 4
    
    def _subad(self):
        self._sub(self.regD)
    
    def _subae(self):
        self._sub(self.regE)
    
    def _subah(self):
        self._sub(self.regH)
    
    def _subal(self):
        self._sub(self.regL)
    
    def _subafromhl(self):
        self._sub(self.bus_access.peekb(self.get_reg_HL()))
    
    def _subaa(self):
        self._sub(self.regA)
     
    # SBC A,*
    def _sbcab(self):
        self._sbc(self.regB)
    
    def _sbcac(self):
        self._sbc(self.regC)
    
    def _sbcad(self):
        self._sbc(self.regD)
    
    def _sbcae(self):
        self._sbc(self.regE)
    
    def _sbcah(self):
        self._sbc(self.regH)
    
    def _sbcal(self):
        self._sbc(self.regL)
    
    def _sbcafromhl(self):
        self._sbc(self.bus_access.peekb(self.get_reg_HL()))
    
    def _sbcaa(self):
        self._sbc(self.regA)
    
    # AND A,*
    def _andab(self):
        self._and(self.regB)
    
    def _andac(self):
        self._and(self.regC)
    
    def _andad(self):
        self._and(self.regD)
    
    def _andae(self):
        self._and(self.regE)
    
    def _andah(self):
        self._and(self.regH)
    
    def _andal(self):
        self._and(self.regL)
    
    def _andafromhl(self):
        self._and(self.bus_access.peekb(self.get_reg_HL()))
    
    def _andaa(self):
        self._and(self.regA)
    
    # XOR A,*
    def _xorab(self):
        self._xor(self.regB)
    
    def _xorac(self):
        self._xor(self.regC)
    
    def _xorad(self):
        self._xor(self.regD)
    
    def _xorae(self):
        self._xor(self.regE)
    
    def _xorah(self):
        self._xor(self.regH)
    
    def _xoral(self):
        self._xor(self.regL)
    
    def _xorafromhl(self):
        self._xor(self.bus_access.peekb(self.get_reg_HL()))
    
    def _xoraa(self):
        self._xor(self.regA)
    
    # OR A,*
    def _orab(self):
        self._or(self.regB)
    
    def _orac(self):
        self._or(self.regC)
    
    def _orad(self):
        self._or(self.regD)
    
    def _orae(self):
        self._or(self.regE)
    
    def _orah(self):
        self._or(self.regH)
    
    def _oral(self):
        self._or(self.regL)
    
    def _orafromhl(self):
        self._or(self.bus_access.peekb(self.get_reg_HL()))
    
    def _oraa(self):
        self._or(self.regA)
    
    # CP A,*
    def _cpab(self):
        self._cp(self.regB)
    
    def _cpac(self):
        self._cp(self.regC)
    
    def _cpad(self):
        self._cp(self.regD)
    
    def _cpae(self):
        self._cp(self.regE)
    
    def _cpah(self):
        self._cp(self.regH)
    
    def _cpal(self):
        self._cp(self.regL)
    
    def _cpafromhl(self):
        self._cp(self.bus_access.peekb(self.get_reg_HL()))
    
    def _cpaa(self):
        self._cp(self.regA)
    
    # RET cc
    def _retnz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = self.memptr = self._pop()
    
    def _retz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self._sz5h3pnFlags & ZERO_MASK) != 0:
            self.regPC = self.memptr = self._pop()
    
    def _retnc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if not self.carryFlag:
            self.regPC = self.memptr = self._pop()
    
    def _retc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self.carryFlag:
            self.regPC = self.memptr = self._pop()
    
    def _retpo(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self._sz5h3pnFlags & PARITY_MASK) == 0:
            self.regPC = self.memptr = self._pop()
    
    def _retpe(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self._sz5h3pnFlags & PARITY_MASK) != 0:
            self.regPC = self.memptr = self._pop()
    
    def _retp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self._sz5h3pnFlags < SIGN_MASK:
            self.regPC = self.memptr = self._pop()
    
    def _retm(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self._sz5h3pnFlags > 0x7f:
            self.regPC = self.memptr = self._pop()
    
    # POP
    def _popbc(self):
        self.set_reg_BC(self._pop())

    def _popde(self):
        self.set_reg_DE(self._pop())

    def _pophl(self):
        self.set_reg_HL(self._pop())

    def _popaf(self):
        self.set_reg_AF(self._pop())
    
    # JP cc,nn
    def _jpnznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jpznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) != 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jpncnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if not self.carryFlag:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jpcnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.carryFlag:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jpponn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & PARITY_MASK) == 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jppenn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & PARITY_MASK) != 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jppnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self._sz5h3pnFlags < SIGN_MASK:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _jpmnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self._sz5h3pnFlags > 0x7f:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    # Various
    def _jphl(self):
        self.regPC = self.get_reg_HL()
    
    def _ldsphl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = self.get_reg_HL()
    
    def _ret(self):
        self.regPC = self.memptr = self._pop()
    
    def _jpnn(self):
        self.memptr = self.regPC = self.bus_access.peekw(self.regPC)

    # CB prefix ----------------------------------------------------------------------------------------------
    # self.rlc *
    def _rlcb(self):
        self.regB = self._rlc(self.regB)

    def _rlcc(self):
        self.regC = self._rlc(self.regC)

    def _rlcd(self):
        self.regD = self._rlc(self.regD)

    def _rlce(self):
        self.regE = self._rlc(self.regE)

    def _rlch(self):
        self.regH = self._rlc(self.regH)

    def _rlcl(self):
        self.regL = self._rlc(self.regL)

    def _rlcfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._rlc(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def _rlc_a(self):
        self.regA = self._rlc(self.regA)

    # self.rrc *
    def _rrcb(self):
        self.regB = self._rrc(self.regB)

    def _rrcc(self):
        self.regC = self._rrc(self.regC)

    def _rrcd(self):
        self.regD = self._rrc(self.regD)

    def _rrce(self):
        self.regE = self._rrc(self.regE)

    def _rrch(self):
        self.regH = self._rrc(self.regH)

    def _rrcl(self):
        self.regL = self._rrc(self.regL)

    def _rrcfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._rrc(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def _rrc_a(self):
        self.regA = self._rrc(self.regA)

    # self.rl *
    def _rlb(self):
        self.regB = self._rl(self.regB)

    def _rl_c(self):
        self.regC = self._rl(self.regC)

    def _rld_(self):
        self.regD = self._rl(self.regD)

    def _rle(self):
        self.regE = self._rl(self.regE)

    def _rlh(self):
        self.regH = self._rl(self.regH)

    def _rll(self):
        self.regL = self._rl(self.regL)

    def _rlfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._rl(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _rl_a(self):
        self.regA = self._rl(self.regA)

    # self.rr *
    def _rrb(self):
        self.regB = self._rr(self.regB)

    def _rr_c(self):
        self.regC = self._rr(self.regC)

    def _rrd_(self):
        self.regD = self._rr(self.regD)

    def _rre(self):
        self.regE = self._rr(self.regE)

    def _rrh(self):
        self.regH = self._rr(self.regH)

    def _rrl(self):
        self.regL = self._rr(self.regL)

    def _rrfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._rr(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _rr_a(self):
        self.regA = self._rr(self.regA)

    # self.sla *
    def _slab(self):
        self.regB = self._sla(self.regB)

    def _slac(self):
        self.regC = self._sla(self.regC)

    def _slad(self):
        self.regD = self._sla(self.regD)

    def _slae(self):
        self.regE = self._sla(self.regE)

    def _slah(self):
        self.regH = self._sla(self.regH)

    def _slal(self):
        self.regL = self._sla(self.regL)

    def _slafromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._sla(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _sla_a(self):
        self.regA = self._sla(self.regA)

    # self.sra *
    def _srab(self):
        self.regB = self._sra(self.regB)
        return 8
    
    def _srac(self):
        self.regC = self._sra(self.regC)

    def _srad(self):
        self.regD = self._sra(self.regD)

    def _srae(self):
        self.regE = self._sra(self.regE)

    def _srah(self):
        self.regH = self._sra(self.regH)

    def _sral(self):
        self.regL = self._sra(self.regL)

    def _srafromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._sra(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def _sra_a(self):
        self.regA = self._sra(self.regA)

    # self.sls *
    def _slsb(self):
        self.regB = self._sll(self.regB)

    def _slsc(self):
        self.regC = self._sll(self.regC)

    def _slsd(self):
        self.regD = self._sll(self.regD)

    def _slse(self):
        self.regE = self._sll(self.regE)

    def _slsh(self):
        self.regH = self._sll(self.regH)

    def _slsl(self):
        self.regL = self._sll(self.regL)

    def _slsfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._sll(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _sls_a(self):
        self.regA = self._sll(self.regA)

    # self.srl *
    def _srlb(self):
        self.regB = self._srl(self.regB)
    
    def _srlc(self):
        self.regC = self._srl(self.regC)

    def _srld(self):
        self.regD = self._srl(self.regD)

    def _srle(self):
        self.regE = self._srl(self.regE)

    def _srlh(self):
        self.regH = self._srl(self.regH)

    def _srll(self):
        self.regL = self._srl(self.regL)

    def _srlfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self._srl(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _srl_a(self):
        self.regA = self._srl(self.regA)

    # self.bit 0, *
    def _bit0b(self):
        self._bit(0x01, self.regB)

    def _bit0c(self):
        self._bit(0x01, self.regC)

    def _bit0d(self):
        self._bit(0x01, self.regD)

    def _bit0e(self):
        self._bit(0x01, self.regE)

    def _bit0h(self):
        self._bit(0x01, self.regH)

    def _bit0l(self):
        self._bit(0x01, self.regL)

    def _bit0fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x01, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def _bit0a(self):
        self._bit(0x01, self.regA)

    # self.bit 1, *
    def _bit1b(self):
        self._bit(0x02, self.regB)

    def _bit1c(self):
        self._bit(0x02, self.regC)

    def _bit1d(self):
        self._bit(0x02, self.regD)

    def _bit1e(self):
        self._bit(0x02, self.regE)

    def _bit1h(self):
        self._bit(0x02, self.regH)

    def _bit1l(self):
        self._bit(0x02, self.regL)

    def _bit1fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x02, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def _bit1a(self):
        self._bit(0x02, self.regA)

    # self.bit 2, *
    def _bit2b(self):
        self._bit(0x04, self.regB)

    def _bit2c(self):
        self._bit(0x04, self.regC)

    def _bit2d(self):
        self._bit(0x04, self.regD)

    def _bit2e(self):
        self._bit(0x04, self.regE)

    def _bit2h(self):
        self._bit(0x04, self.regH)

    def _bit2l(self):
        self._bit(0x04, self.regL)

    def _bit2fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x04, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def _bit2a(self):
        self._bit(0x04, self.regA)

    # self.bit 3, *
    def _bit3b(self):
        self._bit(0x08, self.regB)

    def _bit3c(self):
        self._bit(0x08, self.regC)

    def _bit3d(self):
        self._bit(0x08, self.regD)

    def _bit3e(self):
        self._bit(0x08, self.regE)

    def _bit3h(self):
        self._bit(0x08, self.regH)

    def _bit3l(self):
        self._bit(0x08, self.regL)

    def _bit3fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x08, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def _bit3a(self):
        self._bit(0x08, self.regA)

    # self.bit 4, *
    def _bit4b(self):
        self._bit(0x10, self.regB)

    def _bit4c(self):
        self._bit(0x10, self.regC)

    def _bit4d(self):
        self._bit(0x10, self.regD)

    def _bit4e(self):
        self._bit(0x10, self.regE)

    def _bit4h(self):
        self._bit(0x10, self.regH)

    def _bit4l(self):
        self._bit(0x10, self.regL)

    def _bit4fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x10, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def _bit4a(self):
        self._bit(0x10, self.regA)

    # self.bit 5, *
    def _bit5b(self):
        self._bit(0x20, self.regB)

    def _bit5c(self):
        self._bit(0x20, self.regC)

    def _bit5d(self):
        self._bit(0x20, self.regD)

    def _bit5e(self):
        self._bit(0x20, self.regE)

    def _bit5h(self):
        self._bit(0x20, self.regH)

    def _bit5l(self):
        self._bit(0x20, self.regL)

    def _bit5fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x20, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def _bit5a(self):
        self._bit(0x20, self.regA)

    # self.bit 6, *
    def _bit6b(self):
        self._bit(0x40, self.regB)

    def _bit6c(self):
        self._bit(0x40, self.regC)

    def _bit6d(self):
        self._bit(0x40, self.regD)

    def _bit6e(self):
        self._bit(0x40, self.regE)

    def _bit6h(self):
        self._bit(0x40, self.regH)

    def _bit6l(self):
        self._bit(0x40, self.regL)

    def _bit6fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x40, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def _bit6a(self):
        self._bit(0x40, self.regA)

    # self.bit 7, *
    def _bit7b(self):
        self._bit(0x80, self.regB)

    def _bit7c(self):
        self._bit(0x80, self.regC)

    def _bit7d(self):
        self._bit(0x80, self.regD)

    def _bit7e(self):
        self._bit(0x80, self.regE)

    def _bit7h(self):
        self._bit(0x80, self.regH)

    def _bit7l(self):
        self._bit(0x80, self.regL)

    def _bit7fromhl(self):
        work16 = self.get_reg_HL()
        self._bit(0x80, self.bus_access.peekb(work16))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def _bit7a(self):
        self._bit(0x80, self.regA)

    # self.res 0, *
    def _res0b(self):
        self.regB &= 0xFE

    def _res0c(self):
        self.regC &= 0xFE

    def _res0d(self):
        self.regD &= 0xFE

    def _res0e(self):
        self.regE &= 0xFE

    def _res0h(self):
        self.regH &= 0xFE

    def _res0l(self):
        self.regL &= 0xFE

    def _res0fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFE
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def _res0a(self):
        self.regA &= 0xFE

    # self.res 1, *
    def _res1b(self):
        self.regB &= 0xFD
    
    def _res1c(self):
        self.regC &= 0xFD
    
    def _res1d(self):
        self.regD &= 0xFD
    
    def _res1e(self):
        self.regE &= 0xFD
    
    def _res1h(self):
        self.regH &= 0xFD
    
    def _res1l(self):
        self.regL &= 0xFD
    
    def _res1fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFD
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res1a(self):
        self.regA &= 0xFD
    
    # self.res 2, *
    def _res2b(self):
        self.regB &= 0xFB
    
    def _res2c(self):
        self.regC &= 0xFB
    
    def _res2d(self):
        self.regD &= 0xFB
    
    def _res2e(self):
        self.regE &= 0xFB
    
    def _res2h(self):
        self.regH &= 0xFB
    
    def _res2l(self):
        self.regL &= 0xFB
    
    def _res2fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFB
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res2a(self):
        self.regA &= 0xFB
    
    # self.res 3, *
    def _res3b(self):
        self.regB &= 0xF7
    
    def _res3c(self):
        self.regC &= 0xF7
    
    def _res3d(self):
        self.regD &= 0xF7
    
    def _res3e(self):
        self.regE &= 0xF7
    
    def _res3h(self):
        self.regH &= 0xF7
    
    def _res3l(self):
        self.regL &= 0xF7
    
    def _res3fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xF7
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res3a(self):
        self.regA &= 0xF7
    
    # self.res 4, *
    def _res4b(self):
        self.regB &= 0xEF
    
    def _res4c(self):
        self.regC &= 0xEF
    
    def _res4d(self):
        self.regD &= 0xEF
    
    def _res4e(self):
        self.regE &= 0xEF
    
    def _res4h(self):
        self.regH &= 0xEF
    
    def _res4l(self):
        self.regL &= 0xEF
    
    def _res4fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xEF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res4a(self):
        self.regA &= 0xEF
    
    # self.res 5, *
    def _res5b(self):
        self.regB &= 0xDF
    
    def _res5c(self):
        self.regC &= 0xDF
    
    def _res5d(self):
        self.regD &= 0xDF
    
    def _res5e(self):
        self.regE &= 0xDF
    
    def _res5h(self):
        self.regH &= 0xDF
    
    def _res5l(self):
        self.regL &= 0xDF
    
    def _res5fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xDF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res5a(self):
        self.regA &= 0xDF
    
    # self.res 6, *
    def _res6b(self):
        self.regB &= 0xBF
    
    def _res6c(self):
        self.regC &= 0xBF
    
    def _res6d(self):
        self.regD &= 0xBF
    
    def _res6e(self):
        self.regE &= 0xBF
    
    def _res6h(self):
        self.regH &= 0xBF
    
    def _res6l(self):
        self.regL &= 0xBF
    
    def _res6fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xBF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def _res6a(self):
        self.regA &= 0xBF
    
    # self.res 7, *
    def _res7b(self):
        self.regB &= 0x7F
    
    def _res7c(self):
        self.regC &= 0x7F
    
    def _res7d(self):
        self.regD &= 0x7F
    
    def _res7e(self):
        self.regE &= 0x7F
    
    def _res7h(self):
        self.regH &= 0x7F
    
    def _res7l(self):
        self.regL &= 0x7F
    
    def _res7fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0x7F
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _res7a(self):
        self.regA &= 0x7F
    
    # self.set 0, *
    def _set0b(self):
        self.regB |= 0x01
    
    def _set0c(self):
        self.regC |= 0x01
    
    def _set0d(self):
        self.regD |= 0x01
    
    def _set0e(self):
        self.regE |= 0x01
    
    def _set0h(self):
        self.regH |= 0x01
    
    def _set0l(self):
        self.regL |= 0x01
    
    def _set0fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x01
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set0a(self):
        self.regA |= 0x01
    
    # self.set 1, *
    def _set1b(self):
        self.regB |= 0x02
    
    def _set1c(self):
        self.regC |= 0x02
    
    def _set1d(self):
        self.regD |= 0x02
    
    def _set1e(self):
        self.regE |= 0x02
    
    def _set1h(self):
        self.regH |= 0x02
    
    def _set1l(self):
        self.regL |= 0x02
    
    def _set1fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x02
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set1a(self):
        self.regA |= 0x02
    
    # self.set 2, *
    def _set2b(self):
        self.regB |= 0x04
    
    def _set2c(self):
        self.regC |= 0x04
    
    def _set2d(self):
        self.regD |= 0x04
    
    def _set2e(self):
        self.regE |= 0x04
    
    def _set2h(self):
        self.regH |= 0x04
    
    def _set2l(self):
        self.regL |= 0x04
    
    def _set2fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x04
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set2a(self):
        self.regA |= 0x04
    
    # self.set 3, *
    def _set3b(self):
        self.regB |= 0x08
    
    def _set3c(self):
        self.regC |= 0x08
    
    def _set3d(self):
        self.regD |= 0x08
    
    def _set3e(self):
        self.regE |= 0x08
    
    def _set3h(self):
        self.regH |= 0x08
    
    def _set3l(self):
        self.regL |= 0x08
    
    def _set3fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x08
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set3a(self):
        self.regA |= 0x08
    
    # self.set 4, *
    def _set4b(self):
        self.regB |= 0x10
    
    def _set4c(self):
        self.regC |= 0x10
    
    def _set4d(self):
        self.regD |= 0x10
    
    def _set4e(self):
        self.regE |= 0x10
    
    def _set4h(self):
        self.regH |= 0x10
    
    def _set4l(self):
        self.regL |= 0x10
    
    def _set4fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x10
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set4a(self):
        self.regA |= 0x10
    
    # self.set 5, *
    def _set5b(self):
        self.regB |= 0x20
    
    def _set5c(self):
        self.regC |= 0x20
    
    def _set5d(self):
        self.regD |= 0x20
    
    def _set5e(self):
        self.regE |= 0x20
    
    def _set5h(self):
        self.regH |= 0x20
    
    def _set5l(self):
        self.regL |= 0x20
    
    def _set5fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x20
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set5a(self):
        self.regA |= 0x20
    
    # self.set 6, *
    def _set6b(self):
        self.regB |= 0x40
    
    def _set6c(self):
        self.regC |= 0x40
    
    def _set6d(self):
        self.regD |= 0x40
    
    def _set6e(self):
        self.regE |= 0x40
    
    def _set6h(self):
        self.regH |= 0x40
    
    def _set6l(self):
        self.regL |= 0x40
    
    def _set6fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x40
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set6a(self):
        self.regA |= 0x40
    
    # self.set 7, *
    def _set7b(self):
        self.regB |= 0x80
    
    def _set7c(self):
        self.regC |= 0x80
    
    def _set7d(self):
        self.regD |= 0x80
    
    def _set7e(self):
        self.regE |= 0x80
    
    def _set7h(self):
        self.regH |= 0x80
    
    def _set7l(self):
        self.regL |= 0x80
    
    def _set7fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x80
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def _set7a(self):
        self.regA |= 0x80
    
    def _cb(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        self._cbdict[opcode]()

    def _outna(self):
        work8 = self.bus_access.peekb(self.regPC)
        self.memptr = self.regA << 8
        self.bus_access.out_port(self.memptr | work8, self.regA)
        self.memptr |= ((work8 + 1) & 0xff)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _inan(self):
        self.memptr = (self.regA << 8) | self.bus_access.peekb(self.regPC)
        self.regA = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _exsphl(self):
        work16 = self.regH
        work8 = self.regL
        self.set_reg_HL(self.bus_access.peekw(self.regSP))
        self.bus_access.address_on_bus((self.regSP + 1) & 0xffff, 1)
        self.bus_access.pokeb((self.regSP + 1) & 0xffff, work16)
        self.bus_access.pokeb(self.regSP, work8)
        self.bus_access.address_on_bus(self.regSP, 2)
        self.memptr = self.get_reg_HL()
    
    def _exdehl(self):
        work8 = self.regH
        self.regH = self.regD
        self.regD = work8

        work8 = self.regL
        self.regL = self.regE
        self.regE = work8
    
    def _di(self):
        self.ffIFF1 = False
        self.ffIFF2 = False

    def _ei(self):
        self.ffIFF1 = self.ffIFF2 = True
        self.pendingEI = True
    
    # CALL cc,nn
    def _callnznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & ZERO_MASK) != 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callncnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if not self.carryFlag:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callcnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.carryFlag:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callponn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & PARITY_MASK) == 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callpenn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self._sz5h3pnFlags & PARITY_MASK) != 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callpnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self._sz5h3pnFlags < SIGN_MASK:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def _callmnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self._sz5h3pnFlags > 0x7f:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self._push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    # PUSH
    def _pushbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.get_reg_BC())
    
    def _pushde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.get_reg_DE())
    
    def _pushhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.get_reg_HL())
    
    def _pushaf(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.get_reg_AF())
    
    # op A,N
    def _addan(self):
        self._add(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _adcan(self):
        self._adc(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _suban(self):
        self._sub(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _sbcan(self):
        self._sbc(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _andan(self):
        self._and(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _xoran(self):
        self._xor(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _oran(self):
        self._or(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def _cpan(self):
        self._cp(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    # RST n
    def _rst0(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x00
    
    def _rst8(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x08
    
    def _rst16(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x10
    
    def _rst24(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x18
    
    def _rst32(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x20
    
    def _rst40(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x28
    
    def _rst48(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x30
    
    def _rst56(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(self.regPC)
        self.regPC = self.memptr = 0x38
    
    # Various
    def _callnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
        self._push(self.regPC + 2)
        self.regPC = self.memptr
    
    def _ix(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._ixiydict.get(opcode)
        if code is None:
            self._main_cmds[opcode]()
        else:
            self.regIX = code(self.regIX)

    # ED prefix
    # IN r,(c)
    def _inbfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regB = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regB]
        self._flagQ = True
    
    def _incfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regC = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regC]
        self._flagQ = True

    def _indfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regD = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regD]
        self._flagQ = True
    
    def _inefrombc(self):
        self.memptr = self.get_reg_BC()
        self.regE = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regE]
        self._flagQ = True
    
    def _inhfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regH = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regH]
        self._flagQ = True

    def _inlfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regL = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regL]
        self._flagQ = True
    
    def _infrombc(self):
        self.memptr = self.get_reg_BC()
        in_port = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[in_port]
        self._flagQ = True

    def _inafrombc(self):
        self.memptr = self.get_reg_BC()
        self.regA = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self._sz5h3pnFlags = self._sz53pn_addTable[self.regA]
        self._flagQ = True

    # OUT (c),r
    def _outtocb(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regB)
        self.memptr += 1
    
    def _outtocc(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regC)
        self.memptr += 1
    
    def _outtocd(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regD)
        self.memptr += 1
    
    def _outtoce(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regE)
        self.memptr += 1
    
    def _outtoch(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regH)
        self.memptr += 1
    
    def _outtocl(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regL)
        self.memptr += 1
    
    def _outtoc0(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, 0)
        self.memptr += 1
    
    def _outtoca(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regA)
        self.memptr += 1
    
    # SBC/ADC HL,ss
    def _sbchlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._sbc16(self.get_reg_BC())
    
    def _adchlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._adc16(self.get_reg_BC())
    
    def _sbchlde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._sbc16(self.get_reg_DE())
    
    def _adchlde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._adc16(self.get_reg_DE())
    
    def _sbchlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._sbc16(self.get_reg_HL())
    
    def _adchlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._adc16(self.get_reg_HL())
    
    def _sbchlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._sbc16(self.regSP)
    
    def _adchlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self._adc16(self.regSP)
    
    # LD (nn),ss, LD ss,(nn)
    def _ldtonnbc(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_BC())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _ldbcfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_BC(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def _ldtonnde(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_DE())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def _lddefromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_DE(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def _edldtonnhl(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_HL())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _edldhlfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_HL(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def _ldtonnsp(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.regSP)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def _ldspfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.regSP = self.bus_access.peekw(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    # NEG
    def _nega(self):
        aux = self.regA
        self.regA = 0
        self._sub(aux)
    
    # RETn
    def _retn(self):
        self.ffIFF1 = self.ffIFF2
        self.regPC = self.memptr = self._pop()
    
    def _reti(self):
        self.ffIFF1 = self.ffIFF2
        self.regPC = self.memptr = self._pop()
    
    # IM x
    def _im0(self):
        self.modeINT = IM0
    
    def _im1(self):
        self.modeINT = IM1
    
    def _im2(self):
        self.modeINT = IM2
    
    # LD A,s / LD s,A / RxD
    def _ldia(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regI = self.regA
    
    def _ldra(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.set_reg_R(self.regA)
    
    def _ldai(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regA = self.regI
        self._sz5h3pnFlags = self._sz53n_addTable[self.regA]
        if self.ffIFF2 and not self.bus_access.is_active_INT():
            self._sz5h3pnFlags |= PARITY_MASK
        self._flagQ = True
    
    # Load a with r - (NOT CHECKED)
    def _ldar(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regA = self.get_reg_R()
        self._sz5h3pnFlags = self._sz53n_addTable[self.regA]
        if self.ffIFF2 and not self.bus_access.is_active_INT():
            self._sz5h3pnFlags |= PARITY_MASK
        self._flagQ = True

    # xxIR
    def _ldir(self):
        self._ldi()
        if (self._sz5h3pnFlags & PARITY_MASK) == PARITY_MASK:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_DE() - 1) & 0xffff, 5)
            self._sz5h3pnFlags &= ~FLAG_53_MASK
            self._sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)

    def _cpir(self):
        self._cpi()
        if (self._sz5h3pnFlags & PARITY_MASK) == PARITY_MASK and (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_HL() - 1) & 0xffff, 5)
            self._sz5h3pnFlags &= ~FLAG_53_MASK
            self._sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def _inir(self):
        self._ini()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus((self.get_reg_HL() - 1) & 0xffff, 5)
            self._adjust_inxRoutxRFlags()
    
    def _otir(self):
        self._outi()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus(self.get_reg_BC(), 5)
            self._adjust_inxRoutxRFlags()
    
    # xxDR
    def _lddr(self):
        self._ldd()
        if (self._sz5h3pnFlags & PARITY_MASK) == PARITY_MASK:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_DE() + 1) & 0xffff, 5)
            self._sz5h3pnFlags &= ~FLAG_53_MASK
            self._sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def _cpdr(self):
        self._cpd()
        if (self._sz5h3pnFlags & PARITY_MASK) == PARITY_MASK and (self._sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_HL() + 1) & 0xffff, 5)
            self._sz5h3pnFlags &= ~FLAG_53_MASK
            self._sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def _indr(self):
        self._ind()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus((self.get_reg_HL() + 1) & 0xffff, 5)
            self._adjust_inxRoutxRFlags()
    
    def _otdr(self):
        self._outd()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus(self.get_reg_BC(), 5)
            self._adjust_inxRoutxRFlags()

    def _opcodedd(self):
        self._prefixOpcode = 0xDD

    def _opcodeed(self):
        self._prefixOpcode = 0xED

    def _opcodefd(self):
        self._prefixOpcode = 0xFD

    @staticmethod
    def _ednop():
        return 8
    
    def _ed(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._eddict.get(opcode)
        if code is not None:
            code()

    def _iy(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._ixiydict.get(opcode)
        if code is None:
            self._main_cmds[opcode]()
        else:
            self.regIY = code(self.regIY)

    # IX, IY ops ---------------------------
    # ADD ID, *
    def _addidbc(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self._add16(regIXY, self.get_reg_BC())
    
    def _addidde(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self._add16(regIXY, self.get_reg_DE())
    
    def _addidid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self._add16(regIXY, regIXY)

    def _addidsp(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self._add16(regIXY, self.regSP)
    
    # LD ID, nn
    def _ldidnn(self, _regIXY: int) -> int:
        regIXY = self.bus_access.peekw(self.regPC)
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    def _ldtonnid(self, regIXY: int) -> int:
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, regIXY)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    def _ldidfromnn(self, _regIXY: int) -> int:
        self.memptr = self.bus_access.peekw(self.regPC)
        regIXY = self.bus_access.peekw(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    # INC
    def _incid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        return (regIXY + 1) & 0xffff
    
    def _incidh(self, regIXY: int) -> int:
        return (self._inc8(regIXY >> 8) << 8) | (regIXY & 0xff)
    
    def _incidl(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self._inc8(regIXY & 0xff)
    
    def _incinidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        work8 = self.bus_access.peekb(self.memptr)
        self.bus_access.address_on_bus(self.memptr, 1)
        self.bus_access.pokeb(self.memptr, self._inc8(work8))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # DEC
    def _decid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        return (regIXY - 1) & 0xffff
    
    def _decidh(self, regIXY: int) -> int:
        return (self._dec8(regIXY >> 8) << 8) | (regIXY & 0xff)
    
    def _decidl(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self._dec8(regIXY & 0xff)
    
    def _decinidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        work8 = self.bus_access.peekb(self.memptr)
        self.bus_access.address_on_bus(self.memptr, 1)
        self.bus_access.pokeb(self.memptr, self._dec8(work8))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # LD *, IDH
    def _ldbidh(self, regIXY: int) -> int:
        self.regB = regIXY >> 8
        return regIXY
    
    def _ldcidh(self, regIXY: int) -> int:
        self.regC = regIXY >> 8
        return regIXY
    
    def _lddidh(self, regIXY: int) -> int:
        self.regD = regIXY >> 8
        return regIXY
    
    def _ldeidh(self, regIXY: int) -> int:
        self.regE = regIXY >> 8
        return regIXY
    
    def _ldaidh(self, regIXY: int) -> int:
        self.regA = regIXY >> 8
        return regIXY
    
    # LD *, IDL
    def _ldbidl(self, regIXY: int) -> int:
        self.regB = regIXY & 0xff
        return regIXY
    
    def _ldcidl(self, regIXY: int) -> int:
        self.regC = regIXY & 0xff
        return regIXY
    
    def _lddidl(self, regIXY: int) -> int:
        self.regD = regIXY & 0xff
        return regIXY
    
    def _ldeidl(self, regIXY: int) -> int:
        self.regE = regIXY & 0xff
        return regIXY
    
    def _ldaidl(self, regIXY: int) -> int:
        self.regA = regIXY & 0xff
        return regIXY

    # LD IDH, *
    def _ldidhb(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regB << 8)
    
    def _ldidhc(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regC << 8)

    def _ldidhd(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regD << 8)
    
    def _ldidhe(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regE << 8)
    
    @staticmethod
    def _ldidhidh(regIXY: int) -> int:
        return regIXY
    
    @staticmethod
    def _ldidhidl(regIXY: int) -> int:
        return (regIXY & 0x00ff) | ((regIXY & 0xff) << 8)
    
    def _ldidhn(self, regIXY: int) -> int:
        regIXY = (self.bus_access.peekb(self.regPC) << 8) | (regIXY & 0xff)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldidha(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regA << 8)
    
    # LD IDL, *
    def _ldidlb(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regB
    
    def _ldidlc(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regC
    
    def _ldidld(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regD
    
    def _ldidle(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regE
    
    @staticmethod
    def _ldidlidh(regIXY: int) -> int:
        return (regIXY & 0xff00) | (regIXY >> 8)
    
    @staticmethod
    def _ldidlidl(regIXY: int) -> int:
        return regIXY
    
    def _ldidln(self, regIXY: int) -> int:
        regIXY = (regIXY & 0xff00) | self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def _ldidla(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regA
    
    # LD *, (ID+d)
    def _ldbfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regB = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def _ldcfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regC = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def _lddfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regD = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldefromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regE = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldhfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regH = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldlfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regL = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def _ldafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regA = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # LD (ID+d), *
    def _ldtoiddb(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regB)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoiddc(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regC)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoiddd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regD)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoidde(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regE)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoiddh(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regH)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoiddl(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regL)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _ldtoiddn(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.regPC = (self.regPC + 1) & 0xffff
        work8 = self.bus_access.peekb(self.regPC)
        self.bus_access.address_on_bus(self.regPC, 2)
        self.regPC = (self.regPC + 1) & 0xffff
        self.bus_access.pokeb(self.memptr, work8)
        return regIXY
    
    def _ldtoidda(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regA)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # ADD/ADC A, *
    def _addaidh(self, regIXY: int) -> int:
        self._add(regIXY >> 8)
        return regIXY
    
    def _addaidl(self, regIXY: int) -> int:
        self._add(regIXY & 0xff)
        return regIXY
    
    def _addafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._add(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _adcaidh(self, regIXY: int) -> int:
        self._adc(regIXY >> 8)
        return regIXY
    
    def _adcaidl(self, regIXY: int) -> int:
        self._adc(regIXY & 0xff)
        return regIXY
    
    def _adcafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._adc(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # SUB/SBC A, *
    def _subaidh(self, regIXY: int) -> int:
        self._sub(regIXY >> 8)
        return regIXY

    def _subaidl(self, regIXY: int) -> int:
        self._sub(regIXY & 0xff)
        return regIXY

    def _subafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._sub(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _sbcaidh(self, regIXY: int) -> int:
        self._sbc(regIXY >> 8)
        return regIXY
    
    def _sbcaidl(self, regIXY: int) -> int:
        self._sbc(regIXY & 0xff)
        return regIXY
    
    def _sbcafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._sbc(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # Bitwise OPS
    def _andaidh(self, regIXY: int) -> int:
        self._and(regIXY >> 8)
        return regIXY
    
    def _andaidl(self, regIXY: int) -> int:
        self._and(regIXY & 0xff)
        return regIXY
    
    def _andafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._and(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def _xoraidh(self, regIXY: int) -> int:
        self._xor(regIXY >> 8)
        return regIXY

    def _xoraidl(self, regIXY: int) -> int:
        self._xor(regIXY & 0xff)
        return regIXY

    def _xorafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._xor(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def _oraidh(self, regIXY: int) -> int:
        self._or(regIXY >> 8)
        return regIXY

    def _oraidl(self, regIXY: int) -> int:
        self._or(regIXY & 0xff)
        return regIXY

    def _orafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._or(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # CP A, *
    def _cpaidh(self, regIXY: int) -> int:
        self._cp(regIXY >> 8)
        return regIXY

    def _cpaidl(self, regIXY: int) -> int:
        self._cp(regIXY & 0xff)
        return regIXY

    def _cpafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._cp(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # Various
    def _pushid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self._push(regIXY)
        return regIXY

    def _popid(self, _regIXY: int) -> int:
        return self._pop()
    
    def _jpid(self, regIXY: int) -> int:
        self.regPC = regIXY
        return regIXY
    
    def _ldspid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = regIXY
        return regIXY
    
    def _exfromspid(self, regIXY: int) -> int:
        work16 = regIXY
        regIXY = self.bus_access.peekw(self.regSP)
        self.bus_access.address_on_bus((self.regSP + 1) & 0xffff, 1)
        self.bus_access.pokeb((self.regSP + 1) & 0xffff, work16 >> 8)
        self.bus_access.pokeb(self.regSP, work16)
        self.bus_access.address_on_bus(self.regSP, 2)
        self.memptr = regIXY
        return regIXY

    def _opcodedd_ixy(self, regIXY: int) -> int:
        self._prefixOpcode = 0xDD
        return regIXY

    def _opcodeed_ixy(self, regIXY: int) -> int:
        self._prefixOpcode = 0xED
        return regIXY

    def _opcodefd_ixy(self, regIXY: int) -> int:
        self._prefixOpcode = 0xFD
        return regIXY

    def _idcb(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.regPC = (self.regPC + 1) & 0xffff
        opcode = self.bus_access.peekb(self.regPC)
        self.bus_access.address_on_bus(self.regPC, 2)
        self.regPC = (self.regPC + 1) & 0xffff

        self._idcbdict[opcode](self.memptr)

        return regIXY

    # DDCB/FDCB prefix -----------------------------------------------------
    # DDCB/FDCB opcodes
    # self.rlc *
    def _cbrlcb(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8

    def _cbrlcc(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbrlcd(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbrlce(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbrlch(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbrlcl(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbrlcinhl(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbrlca(self, address):
        work8 = self._rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rrc *
    def _cbrrcb(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbrrcc(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbrrcd(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbrrce(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbrrch(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbrrcl(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbrrcinhl(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbrrca(self, address):
        work8 = self._rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rl *
    def _cbrlb(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbrlc(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbrld(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbrle(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbrlh(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbrll(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbrlinhl(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbrla(self, address):
        work8 = self._rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rr *
    def _cbrrb(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbrrc(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbrrd(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbrre(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbrrh(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbrrl(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbrrinhl(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbrra(self, address):
        work8 = self._rr(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sla *
    def _cbslab(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbslac(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbslad(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8

    def _cbslae(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbslah(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbslal(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbslainhl(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbslaa(self, address):
        work8 = self._sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sra *
    def _cbsrab(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbsrac(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbsrad(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbsrae(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbsrah(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbsral(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbsrainhl(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbsraa(self, address):
        work8 = self._sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sls *
    def _cbslsb(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbslsc(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbslsd(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbslse(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbslsh(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbslsl(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbslsinhl(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbslsa(self, address):
        work8 = self._sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.srl *
    def _cbsrlb(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbsrlc(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbsrld(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbsrle(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbsrlh(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbsrll(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbsrlinhl(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbsrla(self, address):
        work8 = self._srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8

    # self.bit *
    def _cbbit0(self, address):
        self._bit(0x01, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit1(self, address):
        self._bit(0x02, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit2(self, address):
        self._bit(0x04, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit3(self, address):
        self._bit(0x08, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit4(self, address):
        self._bit(0x10, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit5(self, address):
        self._bit(0x20, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit6(self, address):
        self._bit(0x40, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def _cbbit7(self, address):
        self._bit(0x80, self.bus_access.peekb(address))
        self._sz5h3pnFlags = (self._sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    # self.res 0, *
    def _cbres0b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8

    def _cbres0c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres0d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres0e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres0h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres0l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres0inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres0a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 1, *
    def _cbres1b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres1c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres1d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres1e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres1h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres1l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres1inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres1a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 2, *
    def _cbres2b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres2c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres2d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres2e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres2h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres2l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres2inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres2a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 3, *
    def _cbres3b(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres3c(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres3d(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres3e(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres3h(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres3l(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres3inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres3a(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 4, *
    def _cbres4b(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres4c(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres4d(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres4e(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres4h(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres4l(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres4inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres4a(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 5, *
    def _cbres5b(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres5c(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres5d(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres5e(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres5h(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres5l(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres5inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres5a(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 6, *
    def _cbres6b(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres6c(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres6d(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres6e(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres6h(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres6l(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres6inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres6a(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 7, *
    def _cbres7b(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbres7c(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbres7d(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbres7e(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbres7h(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbres7l(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbres7inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbres7a(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 0, *
    def _cbset0b(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset0c(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset0d(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset0e(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset0h(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset0l(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset0inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset0a(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 1, *
    def _cbset1b(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset1c(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset1d(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset1e(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset1h(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset1l(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset1inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset1a(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 2, *
    def _cbset2b(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset2c(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset2d(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset2e(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset2h(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset2l(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset2inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset2a(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 3, *
    def _cbset3b(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset3c(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset3d(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset3e(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset3h(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8

    def _cbset3l(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset3inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset3a(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 4, *
    def _cbset4b(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset4c(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset4d(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset4e(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset4h(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset4l(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset4inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset4a(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 5, *
    def _cbset5b(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset5c(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset5d(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset5e(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset5h(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset5l(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset5inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset5a(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 6, *
    def _cbset6b(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset6c(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset6d(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset6e(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset6h(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset6l(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset6inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset6a(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 7, *
    def _cbset7b(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def _cbset7c(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def _cbset7d(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def _cbset7e(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def _cbset7h(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def _cbset7l(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def _cbset7inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def _cbset7a(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
