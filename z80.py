from typing import Callable

from bus_access import BusAccess
from clock import Clock
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
                 clock: Clock,
                 bus_access: BusAccess,
                 memory: Memory,
                 tstates_test: Callable[[], bool]) -> None:
        self.clock = clock
        self.bus_access = bus_access
        self.memory = memory
        self.tstates_test = tstates_test

        self.show_debug_info = False

        self.clock.tstates = 0

        self.prefixOpcode = 0x00
        self.execDone = False

        self.regA = 0
        self.regB = 0
        self.regC = 0
        self.regD = 0
        self.regE = 0
        self.regH = 0
        self.regL = 0
        self.sz5h3pnFlags = 0
        self.carryFlag = False
        self.flagQ = False
        self.lastFlagQ = False

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

        self.sz53n_addTable = [0] * 256
        self.sz53pn_addTable = [0] * 256
        self.sz53n_subTable = [0] * 256
        self.sz53pn_subTable = [0] * 256

        self.breakpointAt = [False] * 65536

        for idx in range(256):
            if idx > 0x7f:
                self.sz53n_addTable[idx] |= SIGN_MASK

            evenBits = True
            mask = 0x01
            while mask < 0x100:
                if (idx & mask) != 0:
                    evenBits = not evenBits
                mask = mask << 1

            self.sz53n_addTable[idx] |= (idx & FLAG_53_MASK)
            self.sz53n_subTable[idx] = self.sz53n_addTable[idx] | ADDSUB_MASK

            if evenBits:
                self.sz53pn_addTable[idx] = self.sz53n_addTable[idx] | PARITY_MASK
                self.sz53pn_subTable[idx] = self.sz53n_subTable[idx] | PARITY_MASK
            else:
                self.sz53pn_addTable[idx] = self.sz53n_addTable[idx]
                self.sz53pn_subTable[idx] = self.sz53n_subTable[idx]

        self.sz53n_addTable[0] |= ZERO_MASK
        self.sz53pn_addTable[0] |= ZERO_MASK
        self.sz53n_subTable[0] |= ZERO_MASK
        self.sz53pn_subTable[0] |= ZERO_MASK

        self.main_cmds = {
            0x00: self.nop, 0x08: self.ex_af_af, 0x10: self.djnz, 0x18: self.jr, 0x20: self.jrnz, 0x28: self.jrz, 0x30: self.jrnc, 0x38: self.jrc,
            0x01: self.ldbcnn, 0x09: self.addhlbc, 0x11: self.lddenn, 0x19: self.addhlde, 0x21: self.ldhlnn, 0x29: self.addhlhl, 0x31: self.ldspnn, 0x39: self.addhlsp,
            0x02: self.ldtobca, 0x0a: self.ldafrombc, 0x12: self.ldtodea, 0x1a: self.ldafromde, 0x22: self.ldtonnhl, 0x2a: self.ldhlfromnn, 0x32: self.ldtonna, 0x3a: self.ldafromnn,
            0x03: self.incbc, 0x0b: self.decbc, 0x13: self.incde, 0x1b: self.decde, 0x23: self.inchl, 0x2b: self.dechl, 0x33: self.incsp, 0x3b: self.decsp,
            0x04: self.incb, 0x0c: self.incc, 0x14: self.incd, 0x1c: self.ince, 0x24: self.inch, 0x2c: self.incl, 0x34: self.incinhl, 0x3c: self.inca,
            0x05: self.decb, 0x0d: self.decc, 0x15: self.decd, 0x1d: self.dece, 0x25: self.dech, 0x2d: self.decl, 0x35: self.decinhl, 0x3d: self.deca,
            0x06: self.ldbn, 0x0e: self.ldcn, 0x16: self.lddn, 0x1e: self.lden, 0x26: self.ldhn, 0x2e: self.ldln, 0x36: self.ldtohln, 0x3e: self.ldan,
            0x07: self.rlca, 0x0f: self.rrca, 0x17: self.rla, 0x1f: self.rra, 0x27: self.daa, 0x2f: self.cpla, 0x37: self.scf, 0x3f: self.ccf,
            0x40: self.ldbb, 0x41: self.ldbc, 0x42: self.ldbd, 0x43: self.ldbe, 0x44: self.ldbh, 0x45: self.ldbl, 0x46: self.ldbfromhl, 0x47: self.ldba,
            0x48: self.ldcb, 0x49: self.ldcc, 0x4a: self.ldcd, 0x4b: self.ldce, 0x4c: self.ldch, 0x4d: self.ldcl, 0x4e: self.ldcfromhl, 0x4f: self.ldca,
            0x50: self.lddb, 0x51: self.lddc, 0x52: self.lddd, 0x53: self.ldde, 0x54: self.lddh, 0x55: self.lddl, 0x56: self.lddfromhl, 0x57: self.ldda,
            0x58: self.ldeb, 0x59: self.ldec, 0x5a: self.lded, 0x5b: self.ldee, 0x5c: self.ldeh, 0x5d: self.ldel, 0x5e: self.ldefromhl, 0x5f: self.ldea,
            0x60: self.ldhb, 0x61: self.ldhc, 0x62: self.ldhd, 0x63: self.ldhe, 0x64: self.ldhh, 0x65: self.ldhl, 0x66: self.ldhfromhl, 0x67: self.ldha,
            0x68: self.ldlb, 0x69: self.ldlc, 0x6a: self.ldld, 0x6b: self.ldle, 0x6c: self.ldlh, 0x6d: self.ldll, 0x6e: self.ldlfromhl, 0x6f: self.ldla,
            0x70: self.ldtohlb, 0x71: self.ldtohlc, 0x72: self.ldtohld, 0x73: self.ldtohle, 0x74: self.ldtohlh, 0x75: self.ldtohll, 0x76: self.halt, 0x77: self.ldtohla,
            0x78: self.ldab, 0x79: self.ldac, 0x7a: self.ldad, 0x7b: self.ldae, 0x7c: self.ldah, 0x7d: self.ldal, 0x7e: self.ldafromhl, 0x7f: self.ldaa,
            0x80: self.addab, 0x81: self.addac, 0x82: self.addad, 0x83: self.addae, 0x84: self.addah, 0x85: self.addal, 0x86: self.addafromhl, 0x87: self.addaa,
            0x88: self.adcab, 0x89: self.adcac, 0x8a: self.adcad, 0x8b: self.adcae, 0x8c: self.adcah, 0x8d: self.adcal, 0x8e: self.adcafromhl, 0x8f: self.adcaa,
            0x90: self.subab, 0x91: self.subac, 0x92: self.subad, 0x93: self.subae, 0x94: self.subah, 0x95: self.subal, 0x96: self.subafromhl, 0x97: self.subaa,
            0x98: self.sbcab, 0x99: self.sbcac, 0x9a: self.sbcad, 0x9b: self.sbcae, 0x9c: self.sbcah, 0x9d: self.sbcal, 0x9e: self.sbcafromhl, 0x9f: self.sbcaa,
            0xa0: self.andab, 0xa1: self.andac, 0xa2: self.andad, 0xa3: self.andae, 0xa4: self.andah, 0xa5: self.andal, 0xa6: self.andafromhl, 0xa7: self.andaa,
            0xa8: self.xorab, 0xa9: self.xorac, 0xaa: self.xorad, 0xab: self.xorae, 0xac: self.xorah, 0xad: self.xoral, 0xae: self.xorafromhl, 0xaf: self.xoraa,
            0xb0: self.orab, 0xb1: self.orac, 0xb2: self.orad, 0xb3: self.orae, 0xb4: self.orah, 0xb5: self.oral, 0xb6: self.orafromhl, 0xb7: self.oraa,
            0xb8: self.cpab, 0xb9: self.cpac, 0xba: self.cpad, 0xbb: self.cpae, 0xbc: self.cpah, 0xbd: self.cpal, 0xbe: self.cpafromhl, 0xbf: self.cpaa,
            0xc0: self.retnz, 0xc8: self.retz, 0xd0: self.retnc, 0xd8: self.retc, 0xe0: self.retpo, 0xe8: self.retpe, 0xf0: self.retp, 0xf8: self.retm,
            0xc1: self.popbc, 0xd1: self.popde, 0xe1: self.pophl, 0xf1: self.popaf,
            0xc2: self.jpnznn, 0xca: self.jpznn, 0xd2: self.jpncnn, 0xda: self.jpcnn, 0xe2: self.jpponn, 0xea: self.jppenn, 0xf2: self.jppnn, 0xfa: self.jpmnn,
            0xd9: self.exx, 0xe9: self.jphl, 0xf9: self.ldsphl, 0xc9: self.ret, 0xc3: self.jpnn, 0xcb: self.cb, 0xd3: self.outna, 0xdb: self.inan, 0xe3: self.exsphl,
            0xeb: self.exdehl, 0xf3: self.di, 0xfb: self.ei,
            0xc4: self.callnznn, 0xcc: self.callznn, 0xd4: self.callncnn, 0xdc: self.callcnn, 0xe4: self.callponn, 0xec: self.callpenn, 0xf4: self.callpnn, 0xfc: self.callmnn,
            0xc5: self.pushbc, 0xd5: self.pushde, 0xe5: self.pushhl, 0xf5: self.pushaf,
            0xc6: self.addan, 0xce: self.adcan, 0xd6: self.suban, 0xde: self.sbcan, 0xe6: self.andan, 0xee: self.xoran, 0xf6: self.oran, 0xfe: self.cpan,
            0xc7: self.rst0, 0xcf: self.rst8, 0xd7: self.rst16, 0xdf: self.rst24, 0xe7: self.rst32, 0xef: self.rst40, 0xf7: self.rst48, 0xff: self.rst56,
            0xcd: self.callnn, 0xdd: self.ix, 0xed: self.ed, 0xfd: self.iy,
        }

        self._cbdict = {
            0x00: self.rlcb, 0x01: self.rlcc, 0x02: self.rlcd, 0x03: self.rlce, 0x04: self.rlch, 0x05: self.rlcl, 0x06: self.rlcfromhl, 0x07: self.rlc_a,
            0x08: self.rrcb, 0x09: self.rrcc, 0x0a: self.rrcd, 0x0b: self.rrce, 0x0c: self.rrch, 0x0d: self.rrcl, 0x0e: self.rrcfromhl, 0x0f: self.rrc_a,
            0x10: self.rlb, 0x11: self.rl_c, 0x12: self._rld, 0x13: self.rle, 0x14: self.rlh, 0x15: self.rll, 0x16: self.rlfromhl, 0x17: self.rl_a,
            0x18: self.rrb, 0x19: self.rr_c, 0x1a: self._rrd, 0x1b: self.rre, 0x1c: self.rrh, 0x1d: self.rrl, 0x1e: self.rrfromhl, 0x1f: self.rr_a,
            0x20: self.slab, 0x21: self.slac, 0x22: self.slad, 0x23: self.slae, 0x24: self.slah, 0x25: self.slal, 0x26: self.slafromhl, 0x27: self.sla_a,
            0x28: self.srab, 0x29: self.srac, 0x2a: self.srad, 0x2b: self.srae, 0x2c: self.srah, 0x2d: self.sral, 0x2e: self.srafromhl, 0x2f: self.sra_a,
            0x30: self.slsb, 0x31: self.slsc, 0x32: self.slsd, 0x33: self.slse, 0x34: self.slsh, 0x35: self.slsl, 0x36: self.slsfromhl, 0x37: self.sls_a,
            0x38: self.srlb, 0x39: self.srlc, 0x3a: self.srld, 0x3b: self.srle, 0x3c: self.srlh, 0x3d: self.srll, 0x3e: self.srlfromhl, 0x3f: self.srl_a,

            0x40: self.bit0b, 0x41: self.bit0c, 0x42: self.bit0d, 0x43: self.bit0e, 0x44: self.bit0h, 0x45: self.bit0l, 0x46: self.bit0fromhl, 0x47: self.bit0a,
            0x48: self.bit1b, 0x49: self.bit1c, 0x4a: self.bit1d, 0x4b: self.bit1e, 0x4c: self.bit1h, 0x4d: self.bit1l, 0x4e: self.bit1fromhl, 0x4f: self.bit1a,
            0x50: self.bit2b, 0x51: self.bit2c, 0x52: self.bit2d, 0x53: self.bit2e, 0x54: self.bit2h, 0x55: self.bit2l, 0x56: self.bit2fromhl, 0x57: self.bit2a,
            0x58: self.bit3b, 0x59: self.bit3c, 0x5a: self.bit3d, 0x5b: self.bit3e, 0x5c: self.bit3h, 0x5d: self.bit3l, 0x5e: self.bit3fromhl, 0x5f: self.bit3a,
            0x60: self.bit4b, 0x61: self.bit4c, 0x62: self.bit4d, 0x63: self.bit4e, 0x64: self.bit4h, 0x65: self.bit4l, 0x66: self.bit4fromhl, 0x67: self.bit4a,
            0x68: self.bit5b, 0x69: self.bit5c, 0x6a: self.bit5d, 0x6b: self.bit5e, 0x6c: self.bit5h, 0x6d: self.bit5l, 0x6e: self.bit5fromhl, 0x6f: self.bit5a,
            0x70: self.bit6b, 0x71: self.bit6c, 0x72: self.bit6d, 0x73: self.bit6e, 0x74: self.bit6h, 0x75: self.bit6l, 0x76: self.bit6fromhl, 0x77: self.bit6a,
            0x78: self.bit7b, 0x79: self.bit7c, 0x7a: self.bit7d, 0x7b: self.bit7e, 0x7c: self.bit7h, 0x7d: self.bit7l, 0x7e: self.bit7fromhl, 0x7f: self.bit7a,

            0x80: self.res0b, 0x81: self.res0c, 0x82: self.res0d, 0x83: self.res0e, 0x84: self.res0h, 0x85: self.res0l, 0x86: self.res0fromhl, 0x87: self.res0a,
            0x88: self.res1b, 0x89: self.res1c, 0x8a: self.res1d, 0x8b: self.res1e, 0x8c: self.res1h, 0x8d: self.res1l, 0x8e: self.res1fromhl, 0x8f: self.res1a,
            0x90: self.res2b, 0x91: self.res2c, 0x92: self.res2d, 0x93: self.res2e, 0x94: self.res2h, 0x95: self.res2l, 0x96: self.res2fromhl, 0x97: self.res2a,
            0x98: self.res3b, 0x99: self.res3c, 0x9a: self.res3d, 0x9b: self.res3e, 0x9c: self.res3h, 0x9d: self.res3l, 0x9e: self.res3fromhl, 0x9f: self.res3a,
            0xa0: self.res4b, 0xa1: self.res4c, 0xa2: self.res4d, 0xa3: self.res4e, 0xa4: self.res4h, 0xa5: self.res4l, 0xa6: self.res4fromhl, 0xa7: self.res4a,
            0xa8: self.res5b, 0xa9: self.res5c, 0xaa: self.res5d, 0xab: self.res5e, 0xac: self.res5h, 0xad: self.res5l, 0xae: self.res5fromhl, 0xaf: self.res5a,
            0xb0: self.res6b, 0xb1: self.res6c, 0xb2: self.res6d, 0xb3: self.res6e, 0xb4: self.res6h, 0xb5: self.res6l, 0xb6: self.res6fromhl, 0xb7: self.res6a,
            0xb8: self.res7b, 0xb9: self.res7c, 0xba: self.res7d, 0xbb: self.res7e, 0xbc: self.res7h, 0xbd: self.res7l, 0xbe: self.res7fromhl, 0xbf: self.res7a,

            0xc0: self.set0b, 0xc1: self.set0c, 0xc2: self.set0d, 0xc3: self.set0e, 0xc4: self.set0h, 0xc5: self.set0l, 0xc6: self.set0fromhl, 0xc7: self.set0a,
            0xc8: self.set1b, 0xc9: self.set1c, 0xca: self.set1d, 0xcb: self.set1e, 0xcc: self.set1h, 0xcd: self.set1l, 0xce: self.set1fromhl, 0xcf: self.set1a,
            0xd0: self.set2b, 0xd1: self.set2c, 0xd2: self.set2d, 0xd3: self.set2e, 0xd4: self.set2h, 0xd5: self.set2l, 0xd6: self.set2fromhl, 0xd7: self.set2a,
            0xd8: self.set3b, 0xd9: self.set3c, 0xda: self.set3d, 0xdb: self.set3e, 0xdc: self.set3h, 0xdd: self.set3l, 0xde: self.set3fromhl, 0xdf: self.set3a,
            0xe0: self.set4b, 0xe1: self.set4c, 0xe2: self.set4d, 0xe3: self.set4e, 0xe4: self.set4h, 0xe5: self.set4l, 0xe6: self.set4fromhl, 0xe7: self.set4a,
            0xe8: self.set5b, 0xe9: self.set5c, 0xea: self.set5d, 0xeb: self.set5e, 0xec: self.set5h, 0xed: self.set5l, 0xee: self.set5fromhl, 0xef: self.set5a,
            0xf0: self.set6b, 0xf1: self.set6c, 0xf2: self.set6d, 0xf3: self.set6e, 0xf4: self.set6h, 0xf5: self.set6l, 0xf6: self.set6fromhl, 0xf7: self.set6a,
            0xf8: self.set7b, 0xf9: self.set7c, 0xfa: self.set7d, 0xfb: self.set7e, 0xfc: self.set7h, 0xfd: self.set7l, 0xfe: self.set7fromhl, 0xff: self.set7a
        }

        self._eddict = {
            0x40: self.inbfrombc, 0x48: self.incfrombc, 0x50: self.indfrombc, 0x58: self.inefrombc, 0x60: self.inhfrombc, 0x68: self.inlfrombc, 0x70: self.infrombc, 0x78: self.inafrombc,
            0x41: self.outtocb, 0x49: self.outtocc, 0x51: self.outtocd, 0x59: self.outtoce, 0x61: self.outtoch, 0x69: self.outtocl, 0x71: self.outtoc0, 0x79: self.outtoca,
            0x42: self.sbchlbc, 0x4a: self.adchlbc, 0x52: self.sbchlde, 0x5a: self.adchlde, 0x62: self.sbchlhl, 0x6a: self.adchlhl, 0x72: self.sbchlsp, 0x7a: self.adchlsp,
            0x43: self.ldtonnbc, 0x4b: self.ldbcfromnn, 0x53: self.ldtonnde, 0x5b: self.lddefromnn, 0x63: self.edldtonnhl, 0x6b: self.edldhlfromnn, 0x73: self.ldtonnsp, 0x7b: self.ldspfromnn,
            0x44: self.nega, 0x4c: self.nega, 0x54: self.nega, 0x5c: self.nega, 0x64: self.nega, 0x6c: self.nega, 0x74: self.nega, 0x7c: self.nega,
            0x45: self.retn, 0x55: self.retn, 0x65: self.retn, 0x75: self.retn, 0x4d: self.reti, 0x5d: self.reti, 0x6d: self.reti, 0x7d: self.reti,
            0x46: self.im0, 0x4e: self.im0, 0x66: self.im0, 0x6e: self.im0, 0x56: self.im1, 0x76: self.im1, 0x5e: self.im2, 0x7e: self.im2,
            0x47: self.ldia, 0x4f: self.ldra, 0x57: self.ldai, 0x5f: self.ldar, 0x67: self.rrda, 0x6f: self.rlda,
            0xa0: self.ldi, 0xa1: self.cpi, 0xa2: self.ini, 0xa3: self.outi,
            0xa8: self.ldd, 0xa9: self.cpd, 0xaa: self.ind, 0xab: self.outd,
            0xb0: self.ldir, 0xb1: self.cpir, 0xb2: self.inir, 0xb3: self.otir,
            0xb8: self.lddr, 0xb9: self.cpdr, 0xba: self.indr, 0xbb: self.otdr,
            0xdd: self.opcodedd, 0xed: self.opcodeed, 0xfd: self.opcodefd
        }

        self._ixiydict: dict[int, Callable[[int], int]] = {
            0x09: self.addidbc, 0x19: self.addidde, 0x29: self.addidid, 0x39: self.addidsp,
            0x21: self.ldidnn, 0x22: self.ldtonnid, 0x2a: self.ldidfromnn,
            0x23: self.incid, 0x24: self.incidh, 0x2c: self.incidl, 0x34: self.incinidd,
            0x2b: self.decid, 0x25: self.decidh, 0x2d: self.decidl, 0x35: self.decinidd,
            0x44: self.ldbidh, 0x4c: self.ldcidh, 0x54: self.lddidh, 0x5c: self.ldeidh, 0x7c: self.ldaidh,
            0x45: self.ldbidl, 0x4d: self.ldcidl, 0x55: self.lddidl, 0x5d: self.ldeidl, 0x7d: self.ldaidl,
            0x60: self.ldidhb, 0x61: self.ldidhc, 0x62: self.ldidhd, 0x63: self.ldidhe, 0x64: self.ldidhidh, 0x65: self.ldidhidl, 0x26: self.ldidhn, 0x67: self.ldidha,
            0x68: self.ldidlb, 0x69: self.ldidlc, 0x6a: self.ldidld, 0x6b: self.ldidle, 0x6c: self.ldidlidh, 0x6d: self.ldidlidl, 0x2e: self.ldidln, 0x6f: self.ldidla,
            0x46: self.ldbfromidd, 0x4e: self.ldcfromidd, 0x56: self.lddfromidd, 0x5e: self.ldefromidd, 0x66: self.ldhfromidd, 0x6e: self.ldlfromidd, 0x7e: self.ldafromidd,
            0x70: self.ldtoiddb, 0x71: self.ldtoiddc, 0x72: self.ldtoiddd, 0x73: self.ldtoidde, 0x74: self.ldtoiddh, 0x75: self.ldtoiddl, 0x36: self.ldtoiddn, 0x77: self.ldtoidda,
            0x84: self.addaidh, 0x85: self.addaidl, 0x86: self.addafromidd, 0x8c: self.adcaidh, 0x8d: self.adcaidl, 0x8e: self.adcafromidd,
            0x94: self.subaidh, 0x95: self.subaidl, 0x96: self.subafromidd, 0x9c: self.sbcaidh, 0x9d: self.sbcaidl, 0x9e: self.sbcafromidd,
            0xa4: self.andaidh, 0xa5: self.andaidl, 0xa6: self.andafromidd, 0xac: self.xoraidh, 0xad: self.xoraidl, 0xae: self.xorafromidd, 0xb4: self.oraidh, 0xb5: self.oraidl, 0xb6: self.orafromidd,
            0xbc: self.cpaidh, 0xbd: self.cpaidl, 0xbe: self.cpafromidd,
            0xe5: self.pushid, 0xe1: self.popid, 0xe9: self.jpid, 0xf9: self.ldspid, 0xe3: self.exfromspid,
            0xcb: self.idcb, 0xdd: self.opcodedd_ixy, 0xed: self.opcodeed_ixy, 0xfd: self.opcodefd_ixy
        }

        self._idcbdict: dict[int, Callable[[int], None]] = {
            0x00: self.cbrlcb, 0x01: self.cbrlcc, 0x02: self.cbrlcd, 0x03: self.cbrlce, 0x04: self.cbrlch, 0x05: self.cbrlcl, 0x06: self.cbrlcinhl, 0x07: self.cbrlca,
            0x08: self.cbrrcb, 0x09: self.cbrrcc, 0x0a: self.cbrrcd, 0x0b: self.cbrrce, 0x0c: self.cbrrch, 0x0d: self.cbrrcl, 0x0e: self.cbrrcinhl, 0x0f: self.cbrrca,
            0x10: self.cbrlb, 0x11: self.cbrlc, 0x12: self.cbrld, 0x13: self.cbrle, 0x14: self.cbrlh, 0x15: self.cbrll, 0x16: self.cbrlinhl, 0x17: self.cbrla,
            0x18: self.cbrrb, 0x19: self.cbrrc, 0x1a: self.cbrrd, 0x1b: self.cbrre, 0x1c: self.cbrrh, 0x1d: self.cbrrl, 0x1e: self.cbrrinhl, 0x1f: self.cbrra,
            0x20: self.cbslab, 0x21: self.cbslac, 0x22: self.cbslad, 0x23: self.cbslae, 0x24: self.cbslah, 0x25: self.cbslal, 0x26: self.cbslainhl, 0x27: self.cbslaa,
            0x28: self.cbsrab, 0x29: self.cbsrac, 0x2a: self.cbsrad, 0x2b: self.cbsrae, 0x2c: self.cbsrah, 0x2d: self.cbsral, 0x2e: self.cbsrainhl, 0x2f: self.cbsraa,
            0x30: self.cbslsb, 0x31: self.cbslsc, 0x32: self.cbslsd, 0x33: self.cbslse, 0x34: self.cbslsh, 0x35: self.cbslsl, 0x36: self.cbslsinhl, 0x37: self.cbslsa,
            0x38: self.cbsrlb, 0x39: self.cbsrlc, 0x3a: self.cbsrld, 0x3b: self.cbsrle, 0x3c: self.cbsrlh, 0x3d: self.cbsrll, 0x3e: self.cbsrlinhl, 0x3f: self.cbsrla,
            0x40: self.cbbit0, 0x41: self.cbbit0, 0x42: self.cbbit0, 0x43: self.cbbit0, 0x44: self.cbbit0, 0x45: self.cbbit0, 0x46: self.cbbit0, 0x47: self.cbbit0,
            0x48: self.cbbit1, 0x49: self.cbbit1, 0x4a: self.cbbit1, 0x4b: self.cbbit1, 0x4c: self.cbbit1, 0x4d: self.cbbit1, 0x4e: self.cbbit1, 0x4f: self.cbbit1,
            0x50: self.cbbit2, 0x51: self.cbbit2, 0x52: self.cbbit2, 0x53: self.cbbit2, 0x54: self.cbbit2, 0x55: self.cbbit2, 0x56: self.cbbit2, 0x57: self.cbbit2,
            0x58: self.cbbit3, 0x59: self.cbbit3, 0x5a: self.cbbit3, 0x5b: self.cbbit3, 0x5c: self.cbbit3, 0x5d: self.cbbit3, 0x5e: self.cbbit3, 0x5f: self.cbbit3,
            0x60: self.cbbit4, 0x61: self.cbbit4, 0x62: self.cbbit4, 0x63: self.cbbit4, 0x64: self.cbbit4, 0x65: self.cbbit4, 0x66: self.cbbit4, 0x67: self.cbbit4,
            0x68: self.cbbit5, 0x69: self.cbbit5, 0x6a: self.cbbit5, 0x6b: self.cbbit5, 0x6c: self.cbbit5, 0x6d: self.cbbit5, 0x6e: self.cbbit5, 0x6f: self.cbbit5,
            0x70: self.cbbit6, 0x71: self.cbbit6, 0x72: self.cbbit6, 0x73: self.cbbit6, 0x74: self.cbbit6, 0x75: self.cbbit6, 0x76: self.cbbit6, 0x77: self.cbbit6,
            0x78: self.cbbit7, 0x79: self.cbbit7, 0x7a: self.cbbit7, 0x7b: self.cbbit7, 0x7c: self.cbbit7, 0x7d: self.cbbit7, 0x7e: self.cbbit7, 0x7f: self.cbbit7,
            0x80: self.cbres0b, 0x81: self.cbres0c, 0x82: self.cbres0d, 0x83: self.cbres0e, 0x84: self.cbres0h, 0x85: self.cbres0l, 0x86: self.cbres0inhl, 0x87: self.cbres0a,
            0x88: self.cbres1b, 0x89: self.cbres1c, 0x8a: self.cbres1d, 0x8b: self.cbres1e, 0x8c: self.cbres1h, 0x8d: self.cbres1l, 0x8e: self.cbres1inhl, 0x8f: self.cbres1a,
            0x90: self.cbres2b, 0x91: self.cbres2c, 0x92: self.cbres2d, 0x93: self.cbres2e, 0x94: self.cbres2h, 0x95: self.cbres2l, 0x96: self.cbres2inhl, 0x97: self.cbres2a,
            0x98: self.cbres3b, 0x99: self.cbres3c, 0x9a: self.cbres3d, 0x9b: self.cbres3e, 0x9c: self.cbres3h, 0x9d: self.cbres3l, 0x9e: self.cbres3inhl, 0x9f: self.cbres3a,
            0xa0: self.cbres4b, 0xa1: self.cbres4c, 0xa2: self.cbres4d, 0xa3: self.cbres4e, 0xa4: self.cbres4h, 0xa5: self.cbres4l, 0xa6: self.cbres4inhl, 0xa7: self.cbres4a,
            0xa8: self.cbres5b, 0xa9: self.cbres5c, 0xaa: self.cbres5d, 0xab: self.cbres5e, 0xac: self.cbres5h, 0xad: self.cbres5l, 0xae: self.cbres5inhl, 0xaf: self.cbres5a,
            0xb0: self.cbres6b, 0xb1: self.cbres6c, 0xb2: self.cbres6d, 0xb3: self.cbres6e, 0xb4: self.cbres6h, 0xb5: self.cbres6l, 0xb6: self.cbres6inhl, 0xb7: self.cbres6a,
            0xb8: self.cbres7b, 0xb9: self.cbres7c, 0xba: self.cbres7d, 0xbb: self.cbres7e, 0xbc: self.cbres7h, 0xbd: self.cbres7l, 0xbe: self.cbres7inhl, 0xbf: self.cbres7a,
            0xc0: self.cbset0b, 0xc1: self.cbset0c, 0xc2: self.cbset0d, 0xc3: self.cbset0e, 0xc4: self.cbset0h, 0xc5: self.cbset0l, 0xc6: self.cbset0inhl, 0xc7: self.cbset0a,
            0xc8: self.cbset1b, 0xc9: self.cbset1c, 0xca: self.cbset1d, 0xcb: self.cbset1e, 0xcc: self.cbset1h, 0xcd: self.cbset1l, 0xce: self.cbset1inhl, 0xcf: self.cbset1a,
            0xd0: self.cbset2b, 0xd1: self.cbset2c, 0xd2: self.cbset2d, 0xd3: self.cbset2e, 0xd4: self.cbset2h, 0xd5: self.cbset2l, 0xd6: self.cbset2inhl, 0xd7: self.cbset2a,
            0xd8: self.cbset3b, 0xd9: self.cbset3c, 0xda: self.cbset3d, 0xdb: self.cbset3e, 0xdc: self.cbset3h, 0xdd: self.cbset3l, 0xde: self.cbset3inhl, 0xdf: self.cbset3a,
            0xe0: self.cbset4b, 0xe1: self.cbset4c, 0xe2: self.cbset4d, 0xe3: self.cbset4e, 0xe4: self.cbset4h, 0xe5: self.cbset4l, 0xe6: self.cbset4inhl, 0xe7: self.cbset4a,
            0xe8: self.cbset5b, 0xe9: self.cbset5c, 0xea: self.cbset5d, 0xeb: self.cbset5e, 0xec: self.cbset5h, 0xed: self.cbset5l, 0xee: self.cbset5inhl, 0xef: self.cbset5a,
            0xf0: self.cbset6b, 0xf1: self.cbset6c, 0xf2: self.cbset6d, 0xf3: self.cbset6e, 0xf4: self.cbset6h, 0xf5: self.cbset6l, 0xf6: self.cbset6inhl, 0xf7: self.cbset6a,
            0xf8: self.cbset7b, 0xf9: self.cbset7c, 0xfa: self.cbset7d, 0xfb: self.cbset7e, 0xfc: self.cbset7h, 0xfd: self.cbset7l, 0xfe: self.cbset7inhl, 0xff: self.cbset7a
        }

    def interruption(self) -> None:
        self.lastFlagQ = False
        self.halted = False

        self.bus_access.interrupt_handling_time(7)
        self.regR += 1
        self.ffIFF1 = self.ffIFF2 = False
        self.push(self.regPC)
        if self.modeINT == IM2:
            self.regPC = self.bus_access.peekw((self.regI << 8) | 0xff)
        else:
            self.regPC = 0x0038
        self.memptr = self.regPC

    def nmi(self) -> None:
        self.lastFlagQ = False
        self.halted = False

        self.bus_access.fetch_opcode(self.regPC)
        self.bus_access.interrupt_handling_time(1)

        self.regR += 1
        self.ffIFF1 = False
        self.push(self.regPC)
        self.regPC = self.memptr = 0x0066

    def adjustINxROUTxRFlags(self):
        self.sz5h3pnFlags &= ~FLAG_53_MASK
        self.sz5h3pnFlags |= (self.regPC >> 8) & FLAG_53_MASK

        pf = self.sz5h3pnFlags & PARITY_MASK
        if self.carryFlag:
            addsub = 1 - (self.sz5h3pnFlags & ADDSUB_MASK)
            pf ^= self.sz53pn_addTable[(self.regB + addsub) & 0x07] ^ PARITY_MASK
            if (self.regB & 0x0F) == (0x00 if addsub != 1 else 0x0F):
                self.sz5h3pnFlags |= HALFCARRY_MASK
            else:
                self.sz5h3pnFlags &= ~HALFCARRY_MASK
        else:
            pf ^= self.sz53pn_addTable[self.regB & 0x07] ^ PARITY_MASK
            self.sz5h3pnFlags &= ~HALFCARRY_MASK

        if (pf & PARITY_MASK) == PARITY_MASK:
            self.sz5h3pnFlags |= PARITY_MASK
        else:
            self.sz5h3pnFlags &= ~PARITY_MASK

    def execute(self, states_limit: int) -> None:

        while self.clock.tstates < states_limit:
            if self.show_debug_info:
                self.show_registers()

            opcode = self.bus_access.fetch_opcode(self.regPC)
            self.regR += 1

            # if self.prefixOpcode == 0 && breakpointAt.get(regPC):
            #     opCode = NotifyImpl.breakpoint(regPC, opCode);

            if not self.halted:
                self.regPC = (self.regPC + 1) & 0xffff

                if self.prefixOpcode == 0x00:
                    self.flagQ = self.pendingEI = False
                    self.main_cmds[opcode]()
                elif self.prefixOpcode == 0xDD:
                    self.prefixOpcode = 0

                    code = self._ixiydict.get(opcode)
                    if code is None:
                        self.main_cmds[opcode]()
                    else:
                        self.regIX = code(self.regIX)

                elif self.prefixOpcode == 0xED:
                    self.prefixOpcode = 0
                    code = self._eddict.get(opcode)
                    if code is not None:
                        code()
                elif self.prefixOpcode == 0xFD:
                    self.prefixOpcode = 0

                    code = self._ixiydict.get(opcode)
                    if code is None:
                        self.main_cmds[opcode]()
                    else:
                        self.regIY = code(self.regIY)
                else:
                    pass
                    # log.error(String.format("ERROR!: prefixOpcode = %02x, opCode = %02x", prefixOpcode, opCode));

                if self.prefixOpcode != 0x00:
                    continue

                self.lastFlagQ = self.flagQ

                # if execDone:
                #     NotifyImpl.execDone();

            if self.activeNMI:
                self.activeNMI = False
                self.nmi()
                continue

            if self.ffIFF1 and not self.pendingEI and self.bus_access.is_active_INT():
                self.interruption()

            # if not self.ffIFF1 and not self.pendingEI and self.bus_access.is_active_INT():
            #     self.show_debug_info = True

    def show_registers(self):
        print(f"PC: 0x{self.regPC:04x}  "
              f"OPCODE: {self.memory.peekb(self.regPC):#02x}({self.memory.peekb(self.regPC):03d}) "
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
              f"{self.memory.peekb(self.regPC + 7):02x} ")

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
        self.lastFlagQ = False
        self.prefixOpcode = 0x00

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
        return (self.regA << 8) | (self.sz5h3pnFlags | CARRY_MASK if self.carryFlag else self.sz5h3pnFlags)

    def set_reg_AF(self, word: int) -> None:
        self.regA = (word >> 8) & 0xff

        self.sz5h3pnFlags = word & 0xfe
        self.carryFlag = (word & CARRY_MASK) != 0

    def get_reg_AFx(self) -> int: return (self.regAx << 8) | self.regFx

    def set_reg_AFx(self, word: int) -> None:
        self.regAx = (word >> 8) & 0xff
        self.regFx = word & 0xff

    def get_reg_BC(self) -> int: return (self.regB << 8) | self.regC

    def set_reg_BC(self, word: int) -> None:
        self.regB = (word >> 8) & 0xff
        self.regC = word & 0xff

    def inc_reg_BC(self) -> None:
        self.regC += 1
        if self.regC < 0x100: return

        self.regC = 0
        self.regB += 1
        if self.regB < 0x100: return

        self.regB = 0

    def dec_reg_BC(self) -> None:
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

    def inc_reg_DE(self) -> None:
        self.regE += 1
        if self.regE < 0x100: return

        self.regE = 0
        self.regD += 1
        if self.regD < 0x100: return

        self.regD = 0

    def dec_reg_DE(self) -> None:
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

    def inc_reg_HL(self) -> None:
        self.regL += 1
        if self.regL < 0x100: return
        self.regL = 0

        self.regH += 1
        if self.regH < 0x100: return
        self.regH = 0

    def dec_reg_HL(self) -> None:
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

    def is_add_sub_flag(self) -> bool: return (self.sz5h3pnFlags & ADDSUB_MASK) != 0

    def set_add_sub_flag(self, state: bool) -> None:
        if state:
            self.sz5h3pnFlags |= ADDSUB_MASK
        else:
            self.sz5h3pnFlags &= ~ADDSUB_MASK

    def is_par_over_flag(self) -> bool: return (self.sz5h3pnFlags & PARITY_MASK) != 0

    def set_par_over_flag(self, state: bool) -> None:
        if state:
            self.sz5h3pnFlags |= PARITY_MASK
        else:
            self.sz5h3pnFlags &= ~PARITY_MASK

    def is_bit3_flag(self) -> bool: return (self.sz5h3pnFlags & BIT3_MASK) != 0

    def set_bit3_fag(self, state: int) -> None:
        if state:
            self.sz5h3pnFlags |= BIT3_MASK
        else:
            self.sz5h3pnFlags &= ~BIT3_MASK

    def is_half_carry_flag(self): return (self.sz5h3pnFlags & HALFCARRY_MASK) != 0

    def set_half_carry_flag(self, state: bool) -> None:
        if state:
            self.sz5h3pnFlags |= HALFCARRY_MASK
        else:
            self.sz5h3pnFlags &= ~HALFCARRY_MASK

    def is_bit5_flag(self) -> bool: return (self.sz5h3pnFlags & BIT5_MASK) != 0

    def set_bit5_flag(self, state: bool) -> None:
        if state:
            self.sz5h3pnFlags |= BIT5_MASK
        else:
            self.sz5h3pnFlags &= ~BIT5_MASK

    def is_zero_flag(self) -> bool: return (self.sz5h3pnFlags & ZERO_MASK) != 0

    def set_zero_flag(self, state: bool) -> None:
        if state:
            self.sz5h3pnFlags |= ZERO_MASK
        else:
            self.sz5h3pnFlags &= ~ZERO_MASK

    def is_sign_flag(self) -> bool: return self.sz5h3pnFlags >= SIGN_MASK

    def set_sign_flag(self, state) -> None:
        if state:
            self.sz5h3pnFlags |= SIGN_MASK
        else:
            self.sz5h3pnFlags &= ~SIGN_MASK

    def get_flags(self) -> int: return self.sz5h3pnFlags | CARRY_MASK if self.carryFlag else self.sz5h3pnFlags

    def set_flags(self, regF: int) -> None:
        self.sz5h3pnFlags = regF & 0xfe
        self.carryFlag = (regF & CARRY_MASK) != 0

    def trigger_NMI(self) -> None:
        self.activeNMI = True

    def rlc(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        if self.carryFlag:
            oper8 |= CARRY_MASK

        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def rl(self, oper8: int) -> int:
        carry = self.carryFlag
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        if carry:
            oper8 |= CARRY_MASK

        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def sla(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = (oper8 << 1) & 0xfe
        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def sll(self, oper8: int) -> int:
        self.carryFlag = (oper8 > 0x7f)
        oper8 = ((oper8 << 1) | CARRY_MASK) & 0xff
        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def rrc(self, oper8: int) -> int:
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1  # >>>=
        if self.carryFlag:
            oper8 |= SIGN_MASK

        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def rr(self, oper8) -> int:
        carry = self.carryFlag
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1
        if carry:
            oper8 |= SIGN_MASK

        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def rrd(self) -> None:
        aux = (self.regA & 0x0f) << 4
        self.memptr = self.get_reg_HL()
        memHL = self.bus_access.peekb(self.memptr)
        self.regA = (self.regA & 0xf0) | (memHL & 0x0f)
        self.bus_access.address_on_bus(self.memptr, 4)
        self.bus_access.pokeb(self.memptr, (memHL >> 4) | aux)
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA]
        self.memptr += 1
        self.flagQ = True

    def rld(self) -> None:
        aux = self.regA & 0x0f
        self.memptr = self.get_reg_HL()
        memHL = self.bus_access.peekb(self.memptr)
        self.regA = (self.regA & 0xf0) | (memHL >> 4)
        self.bus_access.address_on_bus(self.memptr, 4)
        self.bus_access.pokeb(self.memptr, ((memHL << 4) | aux) & 0xff)
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA]
        self.memptr += 1
        self.flagQ = True

    def sra(self, oper8: int) -> int:
        sign = oper8 & SIGN_MASK
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 = (oper8 >> 1) | sign
        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def srl(self, oper8: int) -> int:
        self.carryFlag = (oper8 & CARRY_MASK) != 0
        oper8 >>= 1
        self.sz5h3pnFlags = self.sz53pn_addTable[oper8]
        self.flagQ = True
        return oper8

    def inc8(self, oper8: int) -> int:
        oper8 = (oper8 + 1) & 0xff

        self.sz5h3pnFlags = self.sz53n_addTable[oper8]

        if (oper8 & 0x0f) == 0:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if oper8 == 0x80:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.flagQ = True
        return oper8

    def dec8(self, oper8: int) -> int:
        oper8 = (oper8 - 1) & 0xff

        self.sz5h3pnFlags = self.sz53n_subTable[oper8]

        if (oper8 & 0x0f) == 0x0f:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if oper8 == 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.flagQ = True
        return oper8

    def add(self, oper8: int) -> None:
        res = self.regA + oper8

        self.carryFlag = res > 0xff
        res &= 0xff
        self.sz5h3pnFlags = self.sz53n_addTable[res]

        if (res & 0x0f) < (self.regA & 0x0f):
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ ~oper8) & (self.regA ^ res)) > 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self.flagQ = True

    def adc(self, oper8: int) -> None:
        res = self.regA + oper8

        if self.carryFlag:
            res += 1

        self.carryFlag = res > 0xff
        res &= 0xff
        self.sz5h3pnFlags = self.sz53n_addTable[res]

        if ((self.regA ^ oper8 ^ res) & 0x10) != 0:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ ~oper8) & (self.regA ^ res)) > 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self.flagQ = True

    def add16(self, reg16: int, oper16: int) -> int:
        oper16 += reg16

        self.carryFlag = oper16 > 0xffff
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | ((oper16 >> 8) & FLAG_53_MASK)
        oper16 &= 0xffff

        if (oper16 & 0x0fff) < (reg16 & 0x0fff):
            self.sz5h3pnFlags |= HALFCARRY_MASK

        self.memptr = reg16 + 1
        self.flagQ = True
        return oper16

    def adc16(self, reg16: int) -> None:
        regHL = self.get_reg_HL()
        self.memptr = regHL + 1

        res = regHL + reg16
        if self.carryFlag:
            res += 1

        self.carryFlag = res > 0xffff
        res &= 0xffff
        self.set_reg_HL(res)

        self.sz5h3pnFlags = self.sz53n_addTable[self.regH]
        if res != 0:
            self.sz5h3pnFlags &= ~ZERO_MASK

        if ((res ^ regHL ^ reg16) & 0x1000) != 0:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((regHL ^ ~reg16) & (regHL ^ res)) > 0x7fff:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.flagQ = True

    def sub(self, oper8: int) -> None:
        res = self.regA - oper8

        self.carryFlag = res < 0
        res &= 0xff
        self.sz5h3pnFlags = self.sz53n_subTable[res]

        if (res & 0x0f) > (self.regA & 0x0f):
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self.flagQ = True

    def sbc(self, oper8: int) -> None:
        res = self.regA - oper8

        if self.carryFlag:
            res -= 1

        self.carryFlag = res < 0
        res &= 0xff
        self.sz5h3pnFlags = self.sz53n_subTable[res]

        if ((self.regA ^ oper8 ^ res) & 0x10) != 0:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.regA = res
        self.flagQ = True

    def sbc16(self, reg16: int) -> None:
        regHL = self.get_reg_HL()
        self.memptr = regHL + 1

        res = regHL - reg16
        if self.carryFlag:
            res -= 1

        self.carryFlag = res < 0
        res &= 0xffff
        self.set_reg_HL(res)

        self.sz5h3pnFlags = self.sz53n_subTable[self.regH]
        if res != 0:
            self.sz5h3pnFlags &= ~ZERO_MASK

        if ((res ^ regHL ^ reg16) & 0x1000) != 0:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((regHL ^ reg16) & (regHL ^ res)) > 0x7fff:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.flagQ = True

    def _and(self, oper8: int) -> None:
        self.regA &= oper8
        self.carryFlag = False
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA] | HALFCARRY_MASK
        self.flagQ = True

    def _xor(self, oper8: int) -> None:
        self.regA = (self.regA ^ oper8) & 0xff
        self.carryFlag = False
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA]
        self.flagQ = True

    def _or(self, oper8: int) -> None:
        self.regA = (self.regA | oper8) & 0xff
        self.carryFlag = False
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA]
        self.flagQ = True

    def cp(self, oper8: int) -> None:
        res = self.regA - (oper8 & 0xff)

        self.carryFlag = res < 0
        res &= 0xff

        self.sz5h3pnFlags = (self.sz53n_addTable[oper8] & FLAG_53_MASK) \
            | (self.sz53n_subTable[res] & FLAG_SZHN_MASK)

        if (res & 0x0f) > (self.regA & 0x0f):
            self.sz5h3pnFlags |= HALFCARRY_MASK

        if ((self.regA ^ oper8) & (self.regA ^ res)) > 0x7f:
            self.sz5h3pnFlags |= OVERFLOW_MASK

        self.flagQ = True

    def daa(self) -> None:
        suma = 0
        carry = self.carryFlag

        if (self.sz5h3pnFlags & HALFCARRY_MASK) != 0 or (self.regA & 0x0f) > 0x09:
            suma = 6

        if carry or (self.regA > 0x99):
            suma |= 0x60

        if self.regA > 0x99:
            carry = True

        if (self.sz5h3pnFlags & ADDSUB_MASK) != 0:
            self.sub(suma)
            self.sz5h3pnFlags = (self.sz5h3pnFlags & HALFCARRY_MASK) | self.sz53pn_subTable[self.regA]
        else:
            self.add(suma)
            self.sz5h3pnFlags = (self.sz5h3pnFlags & HALFCARRY_MASK) | self.sz53pn_addTable[self.regA]

        self.carryFlag = carry
        self.flagQ = True

    def pop(self) -> int:
        word = self.bus_access.peekw(self.regSP)
        self.regSP = (self.regSP + 2) & 0xffff
        return word

    def push(self, word) -> None:
        self.regSP = (self.regSP - 1) & 0xffff
        self.bus_access.pokeb(self.regSP, word >> 8)
        self.regSP = (self.regSP - 1) & 0xffff
        self.bus_access.pokeb(self.regSP, word)

    def ldi(self) -> None:
        work8 = self.bus_access.peekb(self.get_reg_HL())

        regDE = self.get_reg_DE()
        self.bus_access.pokeb(regDE, work8)
        self.bus_access.address_on_bus(regDE, 2)
        self.inc_reg_HL()
        self.inc_reg_DE()
        self.dec_reg_BC()
        work8 += self.regA

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZ_MASK) | (work8 & BIT3_MASK)

        if (work8 & ADDSUB_MASK) != 0:
            self.sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self.sz5h3pnFlags |= PARITY_MASK

        self.flagQ = True

    def ldd(self) -> None:
        work8 = self.bus_access.peekb(self.get_reg_HL())

        regDE = self.get_reg_DE()
        self.bus_access.pokeb(regDE, work8)
        self.bus_access.address_on_bus(regDE, 2)
        self.dec_reg_HL()
        self.dec_reg_DE()
        self.dec_reg_BC()
        work8 += self.regA

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZ_MASK) | (work8 & BIT3_MASK)

        if (work8 & ADDSUB_MASK) != 0:
            self.sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self.sz5h3pnFlags |= PARITY_MASK

        self.flagQ = True

    def cpi(self) -> None:
        regHL = self.get_reg_HL()
        memHL = self.bus_access.peekb(regHL)
        carry = self.carryFlag
        self.cp(memHL)
        self.carryFlag = carry
        self.bus_access.address_on_bus(regHL, 5)
        self.inc_reg_HL()
        self.dec_reg_BC()

        memHL = self.regA - memHL - (1 if (self.sz5h3pnFlags & HALFCARRY_MASK) != 0 else 0)
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHN_MASK) | (memHL & BIT3_MASK)

        if (memHL & ADDSUB_MASK) != 0:
            self.sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self.sz5h3pnFlags |= PARITY_MASK

        self.memptr += 1
        self.flagQ = True

    def cpd(self) -> None:
        regHL = self.get_reg_HL()
        memHL = self.bus_access.peekb(regHL)
        carry = self.carryFlag
        self.cp(memHL)
        self.carryFlag = carry
        self.bus_access.address_on_bus(regHL, 5)
        self.dec_reg_HL()
        self.dec_reg_BC()
        memHL = self.regA - memHL - (1 if (self.sz5h3pnFlags & HALFCARRY_MASK) != 0 else 0)
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHN_MASK) | (memHL & BIT3_MASK)

        if (memHL & ADDSUB_MASK) != 0:
            self.sz5h3pnFlags |= BIT5_MASK

        if self.regC != 0 or self.regB != 0:
            self.sz5h3pnFlags |= PARITY_MASK

        self.memptr -= 1
        self.flagQ = True

    def ini(self) -> None:
        self.memptr = self.get_reg_BC()
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        work8 = self.bus_access.in_port(self.memptr)
        self.bus_access.pokeb(self.get_reg_HL(), work8)

        self.memptr += 1
        self.regB = (self.regB - 1) & 0xff

        self.inc_reg_HL()

        self.sz5h3pnFlags = self.sz53pn_addTable[self.regB]
        if work8 > 0x7f:
            self.sz5h3pnFlags |= ADDSUB_MASK

        self.carryFlag = False
        tmp = work8 + ((self.regC + 1) & 0xff)
        if tmp > 0xff:
            self.sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self.sz53pn_addTable[((tmp & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self.sz5h3pnFlags |= PARITY_MASK
        else:
            self.sz5h3pnFlags &= ~PARITY_MASK

        self.flagQ = True

    def ind(self) -> None:
        self.memptr = self.get_reg_BC()
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        work8 = self.bus_access.in_port(self.memptr)
        self.bus_access.pokeb(self.get_reg_HL(), work8)

        self.memptr -= 1
        self.regB = (self.regB - 1) & 0xff

        self.dec_reg_HL()

        self.sz5h3pnFlags = self.sz53pn_addTable[self.regB]
        if work8 > 0x7f:
            self.sz5h3pnFlags |= ADDSUB_MASK

        self.carryFlag = False

        tmp = work8 + ((self.regC - 1) & 0xff)
        if tmp > 0xff:
            self.sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self.sz53pn_addTable[((tmp & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self.sz5h3pnFlags |= PARITY_MASK
        else:
            self.sz5h3pnFlags &= ~PARITY_MASK

        self.flagQ = True

    def outi(self) -> None:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        self.regB = (self.regB - 1) & 0xff
        self.memptr = self.get_reg_BC()

        work8 = self.bus_access.peekb(self.get_reg_HL())
        self.bus_access.out_port(self.memptr, work8)
        self.memptr += 1

        self.inc_reg_HL()

        self.carryFlag = False
        if work8 > 0x7f:
            self.sz5h3pnFlags = self.sz53n_subTable[self.regB]
        else:
            self.sz5h3pnFlags = self.sz53n_addTable[self.regB]

        if (self.regL + work8) > 0xff:
            self.sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self.sz53pn_addTable[(((self.regL + work8) & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self.sz5h3pnFlags |= PARITY_MASK

        self.flagQ = True

    def outd(self) -> None:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)

        self.regB = (self.regB - 1) & 0xff
        self.memptr = self.get_reg_BC()

        work8 = self.bus_access.peekb(self.get_reg_HL())
        self.bus_access.out_port(self.memptr, work8)
        self.memptr -= 1

        self.dec_reg_HL()

        self.carryFlag = False
        if work8 > 0x7f:
            self.sz5h3pnFlags = self.sz53n_subTable[self.regB]
        else:
            self.sz5h3pnFlags = self.sz53n_addTable[self.regB]

        if (self.regL + work8) > 0xff:
            self.sz5h3pnFlags |= HALFCARRY_MASK
            self.carryFlag = True

        if (self.sz53pn_addTable[(((self.regL + work8) & 0x07) ^ self.regB)] & PARITY_MASK) == PARITY_MASK:
            self.sz5h3pnFlags |= PARITY_MASK

        self.flagQ = True

    def bit(self, mask: int, reg: int) -> None:
        self.set_zero_flag((mask & reg) == 0)

        self.sz5h3pnFlags = (self.sz53n_addTable[reg] & ~FLAG_SZP_MASK) | HALFCARRY_MASK

        if self.is_zero_flag():
            self.sz5h3pnFlags |= (PARITY_MASK | ZERO_MASK)

        if mask == SIGN_MASK and not self.is_zero_flag():
            self.sz5h3pnFlags |= SIGN_MASK

        self.flagQ = True

    @staticmethod
    def nop():
        pass
    
    # EXX
    def exx(self):
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
    def ex_af_af(self):
        work8 = self.regA
        self.regA = self.regAx
        self.regAx = work8

        work8 = self.get_flags()
        self.set_flags(self.regFx)
        self.regFx = work8

    def djnz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        offset = self.bus_access.peeksb(self.regPC)
        self.regB -= 1
        if self.regB != 0:
            self.regB &= 0xff
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC = self.memptr = (self.regPC + offset + 1) & 0xffff
        else:
            self.regPC = (self.regPC + 1) & 0xffff
    
    def jr(self):
        offset = self.bus_access.peeksb(self.regPC)
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regPC = self.memptr = (self.regPC + offset + 1) & 0xffff
    
    def jrnz(self):
        offset = self.bus_access.peeksb(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def jrz(self):
        offset = self.bus_access.peeksb(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) != 0:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def jrnc(self):
        offset = self.bus_access.peeksb(self.regPC)
        if not self.carryFlag:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    def jrc(self):
        offset = self.bus_access.peeksb(self.regPC)
        if self.carryFlag:
            self.bus_access.address_on_bus(self.regPC, 5)
            self.regPC += offset
            self.memptr = self.regPC + 1

        self.regPC = (self.regPC + 1) & 0xffff
    
    # LD self.rr,nn / ADD HL,self.rr
    def ldbcnn(self):
        self.set_reg_BC(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff

    def addhlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.set_reg_HL(self.add16(self.get_reg_HL(), self.get_reg_BC()))

    def lddenn(self):
        self.set_reg_DE(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff
    
    def addhlde(self):
        self.set_reg_HL(self.add16(self.get_reg_HL(), self.get_reg_DE()))

    def ldhlnn(self):
        self.set_reg_HL(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 2) & 0xffff
    
    def addhlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        work16 = self.get_reg_HL()
        self.set_reg_HL(self.add16(work16, work16))
    
    def ldspnn(self):
        self.regSP = self.bus_access.peekw(self.regPC)
        self.regPC = (self.regPC + 2) & 0xffff
    
    def addhlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.set_reg_HL(self.add16(self.get_reg_HL(), self.regSP))
    
    # LD (**),A/A,(**)
    def ldtobca(self):
        self.bus_access.pokeb(self.get_reg_BC(), self.regA)
        self.memptr = self.regA << 8 + (self.regC & 0xff)

    def ldafrombc(self):
        self.memptr = self.get_reg_BC()
        self.regA = self.bus_access.peekb(self.memptr)
        self.memptr += 1

    def ldtodea(self):
        self.bus_access.pokeb(self.get_reg_DE(), self.regA)
        self.memptr = (self.regA << 8) | ((self.regE + 1) & 0xff)
    
    def ldafromde(self):
        self.memptr = self.get_reg_DE()
        self.regA = self.bus_access.peekb(self.get_reg_DE())
        self.memptr += 1

    def ldtonnhl(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_HL())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def ldhlfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_HL(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def ldtonna(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokeb(self.memptr, self.regA)
        self.memptr = (self.regA << 8) | ((self.memptr + 1) & 0xff)
        self.regPC = (self.regPC + 2) & 0xffff
    
    def ldafromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.regA = self.bus_access.peekb(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    # INC/DEC *
    def incbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.inc_reg_BC()

    def decbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.dec_reg_BC()

    def incde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.inc_reg_DE()
    
    def decde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.dec_reg_DE()

    def inchl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.inc_reg_HL()

    def dechl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.dec_reg_HL()
    
    def incsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = (self.regSP + 1) & 0xffff
    
    def decsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = (self.regSP - 1) & 0xffff
    
    # INC *
    def incb(self):
        self.regB = self.inc8(self.regB)

    def incc(self):
        self.regC = self.inc8(self.regC)

    def incd(self):
        self.regD = self.inc8(self.regD)
    
    def ince(self):
        self.regE = self.inc8(self.regE)

    def inch(self):
        self.regH = self.inc8(self.regH)

    def incl(self):
        self.regL = self.inc8(self.regL)

    def incinhl(self):
        work16 = self.get_reg_HL()
        work8 = self.inc8(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def inca(self):
        self.regA = self.inc8(self.regA)
    
    # DEC *
    def decb(self):
        self.regB = self.dec8(self.regB)

    def decc(self):
        self.regC = self.dec8(self.regC)

    def decd(self):
        self.regD = self.dec8(self.regD)
    
    def dece(self):
        self.regE = self.dec8(self.regE)

    def dech(self):
        self.regH = self.dec8(self.regH)

    def decl(self):
        self.regL = self.dec8(self.regL)

    def decinhl(self):
        work16 = self.get_reg_HL()
        work8 = self.dec8(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def deca(self):
        self.regA = self.dec8(self.regA)

    # LD *,N
    def ldbn(self):
        self.regB = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff

    def ldcn(self):
        self.regC = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff

    def lddn(self):
        self.regD = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def lden(self):
        self.regE = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def ldhn(self):
        self.regH = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def ldln(self):
        self.regL = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def ldtohln(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def ldan(self):
        self.regA = self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
    
    # R**A
    def rlca(self):
        self.carryFlag = (self.regA > 0x7f)
        self.regA = (self.regA << 1) & 0xff
        if self.carryFlag:
            self.regA |= CARRY_MASK

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self.flagQ = True

    # Rotate Left through Carry - alters H N C 3 5 flags (CHECKED)
    def rla(self):
        oldCarry = self.carryFlag
        self.carryFlag = (self.regA > 0x7f)
        self.regA = (self.regA << 1) & 0xff
        if oldCarry:
            self.regA |= CARRY_MASK

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self.flagQ = True
    
    # Rotate Right - alters H N C 3 5 flags (CHECKED)
    def rrca(self):
        self.carryFlag = (self.regA & CARRY_MASK) != 0
        self.regA >>= 1
        if self.carryFlag:
            self.regA |= SIGN_MASK

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self.flagQ = True

    # Rotate Right through Carry - alters H N C 3 5 flags (CHECKED)
    def rra(self):
        oldCarry = self.carryFlag
        self.carryFlag = (self.regA & CARRY_MASK) != 0
        self.regA >>= 1
        if oldCarry:
            self.regA |= SIGN_MASK

        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (self.regA & FLAG_53_MASK)
        self.flagQ = True
    
    # Decimal Adjust Accumulator - alters all flags (CHECKED)
    # def daa(self):
    #     ans = self.regA
    #     incr = 0
    #     carry = self._fC
    #
    #     if self._fH or ((ans % 16) > 0x09):
    #         incr |= 0x06
    #
    #     if carry or (ans > 0x9f) or ((ans > 0x8f) and ((ans % 16) > 0x09)):
    #         incr |= 0x60
    #
    #     if ans > 0x99:
    #         carry = True
    #
    #     if self._fN:
    #         self.sub_a(incr)
    #     else:
    #         self.add_a(incr)
    #
    #     ans = self.regA
    #     self._fC = carry
    #     self._fPV = self.parity[ans]
    #     return 4
    
    # One's complement - alters N H 3 5 flags (CHECKED)
    def cpla(self):
        self.regA ^= 0xff
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | HALFCARRY_MASK | (self.regA & FLAG_53_MASK) | ADDSUB_MASK

        self.flagQ = True
    
    # self.set carry flag - alters N H 3 5 C flags (CHECKED)
    def scf(self):
        regQ = self.sz5h3pnFlags if self.lastFlagQ else 0
        self.carryFlag = True
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (((regQ ^ self.sz5h3pnFlags) | self.regA) & FLAG_53_MASK)
        self.flagQ = True
    
    # Complement carry flag - alters N 3 5 C flags (CHECKED)
    def ccf(self):
        regQ = self.sz5h3pnFlags if self.lastFlagQ else 0
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZP_MASK) | (((regQ ^ self.sz5h3pnFlags) | self.regA) & FLAG_53_MASK)
        if self.carryFlag:
            self.sz5h3pnFlags |= HALFCARRY_MASK

        self.carryFlag = not self.carryFlag
        self.flagQ = True
    
    # LD B,*
    @staticmethod
    def ldbb():
        pass
    
    def ldbc(self):
        self.regB = self.regC

    def ldbd(self):
        self.regB = self.regD

    def ldbe(self):
        self.regB = self.regE

    def ldbh(self):
        self.regB = self.regH

    def ldbl(self):
        self.regB = self.regL

    def ldbfromhl(self):
        self.regB = self.bus_access.peekb(self.get_reg_HL())

    def ldba(self):
        self.regB = self.regA

    # LD C,*
    def ldcb(self):
        self.regC = self.regB

    @staticmethod
    def ldcc():
        pass

    def ldcd(self):
        self.regC = self.regD

    def ldce(self):
        self.regC = self.regE

    def ldch(self):
        self.regC = self.regH

    def ldcl(self):
        self.regC = self.regL

    def ldcfromhl(self):
        self.regC = self.bus_access.peekb(self.get_reg_HL())

    def ldca(self):
        self.regC = self.regA

    # LD D,*
    def lddb(self):
        self.regD = self.regB

    def lddc(self):
        self.regD = self.regC

    @staticmethod
    def lddd():
        pass

    def ldde(self):
        self.regD = self.regE

    def lddh(self):
        self.regD = self.regH

    def lddl(self):
        self.regD = self.regL

    def lddfromhl(self):
        self.regD = self.bus_access.peekb(self.get_reg_HL())

    def ldda(self):
        self.regD = self.regA

    # LD E,*
    def ldeb(self):
        self.regE = self.regB

    def ldec(self):
        self.regE = self.regC

    def lded(self):
        self.regE = self.regD

    @staticmethod
    def ldee():
        pass
    
    def ldeh(self):
        self.regE = self.regH

    def ldel(self):
        self.regE = self.regL

    def ldefromhl(self):
        self.regE = self.bus_access.peekb(self.get_reg_HL())

    def ldea(self):
        self.regE = self.regA

    # LD H,*
    def ldhb(self):
        self.regH = self.regB

    def ldhc(self):
        self.regH = self.regC

    def ldhd(self):
        self.regH = self.regD

    def ldhe(self):
        self.regH = self.regE

    @staticmethod
    def ldhh():
        pass
    
    def ldhl(self):
        self.regH = self.regL

    def ldhfromhl(self):
        self.regH = self.bus_access.peekb(self.get_reg_HL())

    def ldha(self):
        self.regH = self.regA

    # LD L,*
    def ldlb(self):
        self.regL = self.regB

    def ldlc(self):
        self.regL = self.regC

    def ldld(self):
        self.regL = self.regD

    def ldle(self):
        self.regL = self.regE

    def ldlh(self):
        self.regL = self.regH

    @staticmethod
    def ldll():
        pass
    
    def ldlfromhl(self):
        self.regL = self.bus_access.peekb(self.get_reg_HL())

    def ldla(self):
        self.regL = self.regA

    # LD (HL),*
    def ldtohlb(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regB)

    def ldtohlc(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regC)

    def ldtohld(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regD)

    def ldtohle(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regE)

    def ldtohlh(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regH)

    def ldtohll(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regL)

    def ldtohla(self):
        self.bus_access.pokeb(self.get_reg_HL(), self.regA)

    def halt(self):
        self.halted = True

    # LD A,*
    def ldab(self):
        self.regA = self.regB

    def ldac(self):
        self.regA = self.regC

    def ldad(self):
        self.regA = self.regD

    def ldae(self):
        self.regA = self.regE

    def ldah(self):
        self.regA = self.regH

    def ldal(self):
        self.regA = self.regL

    def ldafromhl(self):
        self.regA = self.bus_access.peekb(self.get_reg_HL())

    @staticmethod
    def ldaa():
        pass
    
    # ADD A,*
    def addab(self):
        self.add(self.regB)

    def addac(self):
        self.add(self.regC)

    def addad(self):
        self.add(self.regD)

    def addae(self):
        self.add(self.regE)

    def addah(self):
        self.add(self.regH)
    
    def addal(self):
        self.add(self.regL)
    
    def addafromhl(self):
        self.add(self.bus_access.peekb(self.get_reg_HL()))
    
    def addaa(self):
        self.add(self.regA)
    
    # ADC A,*
    def adcab(self):
        self.adc(self.regB)
    
    def adcac(self):
        self.adc(self.regC)
    
    def adcad(self):
        self.adc(self.regD)
    
    def adcae(self):
        self.adc(self.regE)
    
    def adcah(self):
        self.adc(self.regH)
        return 4
    
    def adcal(self):
        self.adc(self.regL)
    
    def adcafromhl(self):
        self.adc(self.bus_access.peekb(self.get_reg_HL()))
    
    def adcaa(self):
        self.adc(self.regA)
    
    # SUB A,*
    def subab(self):
        self.sub(self.regB)
    
    def subac(self):
        self.sub(self.regC)
        return 4
    
    def subad(self):
        self.sub(self.regD)
    
    def subae(self):
        self.sub(self.regE)
    
    def subah(self):
        self.sub(self.regH)
    
    def subal(self):
        self.sub(self.regL)
    
    def subafromhl(self):
        self.sub(self.bus_access.peekb(self.get_reg_HL()))
    
    def subaa(self):
        self.sub(self.regA)
     
    # SBC A,*
    def sbcab(self):
        self.sbc(self.regB)
    
    def sbcac(self):
        self.sbc(self.regC)
    
    def sbcad(self):
        self.sbc(self.regD)
    
    def sbcae(self):
        self.sbc(self.regE)
    
    def sbcah(self):
        self.sbc(self.regH)
    
    def sbcal(self):
        self.sbc(self.regL)
    
    def sbcafromhl(self):
        self.sbc(self.bus_access.peekb(self.get_reg_HL()))
    
    def sbcaa(self):
        self.sbc(self.regA)
    
    # AND A,*
    def andab(self):
        self._and(self.regB)
    
    def andac(self):
        self._and(self.regC)
    
    def andad(self):
        self._and(self.regD)
    
    def andae(self):
        self._and(self.regE)
    
    def andah(self):
        self._and(self.regH)
    
    def andal(self):
        self._and(self.regL)
    
    def andafromhl(self):
        self._and(self.bus_access.peekb(self.get_reg_HL()))
    
    def andaa(self):
        self._and(self.regA)
    
    # XOR A,*
    def xorab(self):
        self._xor(self.regB)
    
    def xorac(self):
        self._xor(self.regC)
    
    def xorad(self):
        self._xor(self.regD)
    
    def xorae(self):
        self._xor(self.regE)
    
    def xorah(self):
        self._xor(self.regH)
    
    def xoral(self):
        self._xor(self.regL)
    
    def xorafromhl(self):
        self._xor(self.bus_access.peekb(self.get_reg_HL()))
    
    def xoraa(self):
        self._xor(self.regA)
    
    # OR A,*
    def orab(self):
        self._or(self.regB)
    
    def orac(self):
        self._or(self.regC)
    
    def orad(self):
        self._or(self.regD)
    
    def orae(self):
        self._or(self.regE)
    
    def orah(self):
        self._or(self.regH)
    
    def oral(self):
        self._or(self.regL)
    
    def orafromhl(self):
        self._or(self.bus_access.peekb(self.get_reg_HL()))
    
    def oraa(self):
        self._or(self.regA)
    
    # CP A,*
    def cpab(self):
        self.cp(self.regB)
    
    def cpac(self):
        self.cp(self.regC)
    
    def cpad(self):
        self.cp(self.regD)
    
    def cpae(self):
        self.cp(self.regE)
    
    def cpah(self):
        self.cp(self.regH)
    
    def cpal(self):
        self.cp(self.regL)
    
    def cpafromhl(self):
        self.cp(self.bus_access.peekb(self.get_reg_HL()))
    
    def cpaa(self):
        self.cp(self.regA)
    
    # RET cc
    def retnz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = self.memptr = self.pop()
    
    def retz(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self.sz5h3pnFlags & ZERO_MASK) != 0:
            self.regPC = self.memptr = self.pop()
    
    def retnc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if not self.carryFlag:
            self.regPC = self.memptr = self.pop()
    
    def retc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self.carryFlag:
            self.regPC = self.memptr = self.pop()
    
    def retpo(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self.sz5h3pnFlags & PARITY_MASK) == 0:
            self.regPC = self.memptr = self.pop()
    
    def retpe(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if (self.sz5h3pnFlags & PARITY_MASK) != 0:
            self.regPC = self.memptr = self.pop()
    
    def retp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self.sz5h3pnFlags < SIGN_MASK:
            self.regPC = self.memptr = self.pop()
    
    def retm(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        if self.sz5h3pnFlags > 0x7f:
            self.regPC = self.memptr = self.pop()
    
    # POP
    def popbc(self):
        self.set_reg_BC(self.pop())

    def popde(self):
        self.set_reg_DE(self.pop())

    def pophl(self):
        self.set_reg_HL(self.pop())

    def popaf(self):
        self.set_reg_AF(self.pop())
    
    # JP cc,nn
    def jpnznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jpznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) != 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jpncnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if not self.carryFlag:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jpcnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.carryFlag:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jpponn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & PARITY_MASK) == 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jppenn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & PARITY_MASK) != 0:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jppnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.sz5h3pnFlags < SIGN_MASK:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def jpmnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.sz5h3pnFlags > 0x7f:
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    # Various
    def jphl(self):
        self.regPC = self.get_reg_HL()
    
    def ldsphl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = self.get_reg_HL()
    
    def ret(self):
        self.regPC = self.memptr = self.pop()
    
    def jpnn(self):
        self.memptr = self.regPC = self.bus_access.peekw(self.regPC)

    # CB prefix ----------------------------------------------------------------------------------------------
    # self.rlc *
    def rlcb(self):
        self.regB = self.rlc(self.regB)

    def rlcc(self):
        self.regC = self.rlc(self.regC)

    def rlcd(self):
        self.regD = self.rlc(self.regD)

    def rlce(self):
        self.regE = self.rlc(self.regE)

    def rlch(self):
        self.regH = self.rlc(self.regH)

    def rlcl(self):
        self.regL = self.rlc(self.regL)

    def rlcfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.rlc(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def rlc_a(self):
        self.regA = self.rlc(self.regA)

    # self.rrc *
    def rrcb(self):
        self.regB = self.rrc(self.regB)

    def rrcc(self):
        self.regC = self.rrc(self.regC)

    def rrcd(self):
        self.regD = self.rrc(self.regD)

    def rrce(self):
        self.regE = self.rrc(self.regE)

    def rrch(self):
        self.regH = self.rrc(self.regH)

    def rrcl(self):
        self.regL = self.rrc(self.regL)

    def rrcfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.rrc(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def rrc_a(self):
        self.regA = self.rrc(self.regA)

    # self.rl *
    def rlb(self):
        self.regB = self.rl(self.regB)

    def rl_c(self):
        self.regC = self.rl(self.regC)

    def _rld(self):
        self.regD = self.rl(self.regD)

    def rle(self):
        self.regE = self.rl(self.regE)

    def rlh(self):
        self.regH = self.rl(self.regH)

    def rll(self):
        self.regL = self.rl(self.regL)

    def rlfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.rl(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def rl_a(self):
        self.regA = self.rl(self.regA)

    # self.rr *
    def rrb(self):
        self.regB = self.rr(self.regB)

    def rr_c(self):
        self.regC = self.rr(self.regC)

    def _rrd(self):
        self.regD = self.rr(self.regD)

    def rre(self):
        self.regE = self.rr(self.regE)

    def rrh(self):
        self.regH = self.rr(self.regH)

    def rrl(self):
        self.regL = self.rr(self.regL)

    def rrfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.rr(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def rr_a(self):
        self.regA = self.rr(self.regA)

    # self.sla *
    def slab(self):
        self.regB = self.sla(self.regB)

    def slac(self):
        self.regC = self.sla(self.regC)

    def slad(self):
        self.regD = self.sla(self.regD)

    def slae(self):
        self.regE = self.sla(self.regE)

    def slah(self):
        self.regH = self.sla(self.regH)

    def slal(self):
        self.regL = self.sla(self.regL)

    def slafromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.sla(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def sla_a(self):
        self.regA = self.sla(self.regA)

    # self.sra *
    def srab(self):
        self.regB = self.sra(self.regB)
        return 8
    
    def srac(self):
        self.regC = self.sra(self.regC)

    def srad(self):
        self.regD = self.sra(self.regD)

    def srae(self):
        self.regE = self.sra(self.regE)

    def srah(self):
        self.regH = self.sra(self.regH)

    def sral(self):
        self.regL = self.sra(self.regL)

    def srafromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.sra(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def sra_a(self):
        self.regA = self.sra(self.regA)

    # self.sls *
    def slsb(self):
        self.regB = self.sll(self.regB)

    def slsc(self):
        self.regC = self.sll(self.regC)

    def slsd(self):
        self.regD = self.sll(self.regD)

    def slse(self):
        self.regE = self.sll(self.regE)

    def slsh(self):
        self.regH = self.sll(self.regH)

    def slsl(self):
        self.regL = self.sll(self.regL)

    def slsfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.sll(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def sls_a(self):
        self.regA = self.sll(self.regA)

    # self.srl *
    def srlb(self):
        self.regB = self.srl(self.regB)
    
    def srlc(self):
        self.regC = self.srl(self.regC)

    def srld(self):
        self.regD = self.srl(self.regD)

    def srle(self):
        self.regE = self.srl(self.regE)

    def srlh(self):
        self.regH = self.srl(self.regH)

    def srll(self):
        self.regL = self.srl(self.regL)

    def srlfromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.srl(self.bus_access.peekb(work16))
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def srl_a(self):
        self.regA = self.srl(self.regA)

    # self.bit 0, *
    def bit0b(self):
        self.bit(0x01, self.regB)

    def bit0c(self):
        self.bit(0x01, self.regC)

    def bit0d(self):
        self.bit(0x01, self.regD)

    def bit0e(self):
        self.bit(0x01, self.regE)

    def bit0h(self):
        self.bit(0x01, self.regH)

    def bit0l(self):
        self.bit(0x01, self.regL)

    def bit0fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x01, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def bit0a(self):
        self.bit(0x01, self.regA)

    # self.bit 1, *
    def bit1b(self):
        self.bit(0x02, self.regB)

    def bit1c(self):
        self.bit(0x02, self.regC)

    def bit1d(self):
        self.bit(0x02, self.regD)

    def bit1e(self):
        self.bit(0x02, self.regE)

    def bit1h(self):
        self.bit(0x02, self.regH)

    def bit1l(self):
        self.bit(0x02, self.regL)

    def bit1fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x02, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def bit1a(self):
        self.bit(0x02, self.regA)

    # self.bit 2, *
    def bit2b(self):
        self.bit(0x04, self.regB)

    def bit2c(self):
        self.bit(0x04, self.regC)

    def bit2d(self):
        self.bit(0x04, self.regD)

    def bit2e(self):
        self.bit(0x04, self.regE)

    def bit2h(self):
        self.bit(0x04, self.regH)

    def bit2l(self):
        self.bit(0x04, self.regL)

    def bit2fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x04, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def bit2a(self):
        self.bit(0x04, self.regA)

    # self.bit 3, *
    def bit3b(self):
        self.bit(0x08, self.regB)

    def bit3c(self):
        self.bit(0x08, self.regC)

    def bit3d(self):
        self.bit(0x08, self.regD)

    def bit3e(self):
        self.bit(0x08, self.regE)

    def bit3h(self):
        self.bit(0x08, self.regH)

    def bit3l(self):
        self.bit(0x08, self.regL)

    def bit3fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x08, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def bit3a(self):
        self.bit(0x08, self.regA)

    # self.bit 4, *
    def bit4b(self):
        self.bit(0x10, self.regB)

    def bit4c(self):
        self.bit(0x10, self.regC)

    def bit4d(self):
        self.bit(0x10, self.regD)

    def bit4e(self):
        self.bit(0x10, self.regE)

    def bit4h(self):
        self.bit(0x10, self.regH)

    def bit4l(self):
        self.bit(0x10, self.regL)

    def bit4fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x10, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)

    def bit4a(self):
        self.bit(0x10, self.regA)

    # self.bit 5, *
    def bit5b(self):
        self.bit(0x20, self.regB)

    def bit5c(self):
        self.bit(0x20, self.regC)

    def bit5d(self):
        self.bit(0x20, self.regD)

    def bit5e(self):
        self.bit(0x20, self.regE)

    def bit5h(self):
        self.bit(0x20, self.regH)

    def bit5l(self):
        self.bit(0x20, self.regL)

    def bit5fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x20, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def bit5a(self):
        self.bit(0x20, self.regA)

    # self.bit 6, *
    def bit6b(self):
        self.bit(0x40, self.regB)

    def bit6c(self):
        self.bit(0x40, self.regC)

    def bit6d(self):
        self.bit(0x40, self.regD)

    def bit6e(self):
        self.bit(0x40, self.regE)

    def bit6h(self):
        self.bit(0x40, self.regH)

    def bit6l(self):
        self.bit(0x40, self.regL)

    def bit6fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x40, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def bit6a(self):
        self.bit(0x40, self.regA)

    # self.bit 7, *
    def bit7b(self):
        self.bit(0x80, self.regB)

    def bit7c(self):
        self.bit(0x80, self.regC)

    def bit7d(self):
        self.bit(0x80, self.regD)

    def bit7e(self):
        self.bit(0x80, self.regE)

    def bit7h(self):
        self.bit(0x80, self.regH)

    def bit7l(self):
        self.bit(0x80, self.regL)

    def bit7fromhl(self):
        work16 = self.get_reg_HL()
        self.bit(0x80, self.bus_access.peekb(work16))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((self.memptr >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(work16, 1)
    
    def bit7a(self):
        self.bit(0x80, self.regA)

    # self.res 0, *
    def res0b(self):
        self.regB &= 0xFE

    def res0c(self):
        self.regC &= 0xFE

    def res0d(self):
        self.regD &= 0xFE

    def res0e(self):
        self.regE &= 0xFE

    def res0h(self):
        self.regH &= 0xFE

    def res0l(self):
        self.regL &= 0xFE

    def res0fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFE
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def res0a(self):
        self.regA &= 0xFE

    # self.res 1, *
    def res1b(self):
        self.regB &= 0xFD
    
    def res1c(self):
        self.regC &= 0xFD
    
    def res1d(self):
        self.regD &= 0xFD
    
    def res1e(self):
        self.regE &= 0xFD
    
    def res1h(self):
        self.regH &= 0xFD
    
    def res1l(self):
        self.regL &= 0xFD
    
    def res1fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFD
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res1a(self):
        self.regA &= 0xFD
    
    # self.res 2, *
    def res2b(self):
        self.regB &= 0xFB
    
    def res2c(self):
        self.regC &= 0xFB
    
    def res2d(self):
        self.regD &= 0xFB
    
    def res2e(self):
        self.regE &= 0xFB
    
    def res2h(self):
        self.regH &= 0xFB
    
    def res2l(self):
        self.regL &= 0xFB
    
    def res2fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xFB
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res2a(self):
        self.regA &= 0xFB
    
    # self.res 3, *
    def res3b(self):
        self.regB &= 0xF7
    
    def res3c(self):
        self.regC &= 0xF7
    
    def res3d(self):
        self.regD &= 0xF7
    
    def res3e(self):
        self.regE &= 0xF7
    
    def res3h(self):
        self.regH &= 0xF7
    
    def res3l(self):
        self.regL &= 0xF7
    
    def res3fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xF7
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res3a(self):
        self.regA &= 0xF7
    
    # self.res 4, *
    def res4b(self):
        self.regB &= 0xEF
    
    def res4c(self):
        self.regC &= 0xEF
    
    def res4d(self):
        self.regD &= 0xEF
    
    def res4e(self):
        self.regE &= 0xEF
    
    def res4h(self):
        self.regH &= 0xEF
    
    def res4l(self):
        self.regL &= 0xEF
    
    def res4fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xEF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res4a(self):
        self.regA &= 0xEF
    
    # self.res 5, *
    def res5b(self):
        self.regB &= 0xDF
    
    def res5c(self):
        self.regC &= 0xDF
    
    def res5d(self):
        self.regD &= 0xDF
    
    def res5e(self):
        self.regE &= 0xDF
    
    def res5h(self):
        self.regH &= 0xDF
    
    def res5l(self):
        self.regL &= 0xDF
    
    def res5fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xDF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res5a(self):
        self.regA &= 0xDF
    
    # self.res 6, *
    def res6b(self):
        self.regB &= 0xBF
    
    def res6c(self):
        self.regC &= 0xBF
    
    def res6d(self):
        self.regD &= 0xBF
    
    def res6e(self):
        self.regE &= 0xBF
    
    def res6h(self):
        self.regH &= 0xBF
    
    def res6l(self):
        self.regL &= 0xBF
    
    def res6fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0xBF
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)

    def res6a(self):
        self.regA &= 0xBF
    
    # self.res 7, *
    def res7b(self):
        self.regB &= 0x7F
    
    def res7c(self):
        self.regC &= 0x7F
    
    def res7d(self):
        self.regD &= 0x7F
    
    def res7e(self):
        self.regE &= 0x7F
    
    def res7h(self):
        self.regH &= 0x7F
    
    def res7l(self):
        self.regL &= 0x7F
    
    def res7fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) & 0x7F
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def res7a(self):
        self.regA &= 0x7F
    
    # self.set 0, *
    def set0b(self):
        self.regB |= 0x01
    
    def set0c(self):
        self.regC |= 0x01
    
    def set0d(self):
        self.regD |= 0x01
    
    def set0e(self):
        self.regE |= 0x01
    
    def set0h(self):
        self.regH |= 0x01
    
    def set0l(self):
        self.regL |= 0x01
    
    def set0fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x01
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set0a(self):
        self.regA |= 0x01
    
    # self.set 1, *
    def set1b(self):
        self.regB |= 0x02
    
    def set1c(self):
        self.regC |= 0x02
    
    def set1d(self):
        self.regD |= 0x02
    
    def set1e(self):
        self.regE |= 0x02
    
    def set1h(self):
        self.regH |= 0x02
    
    def set1l(self):
        self.regL |= 0x02
    
    def set1fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x02
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set1a(self):
        self.regA |= 0x02
    
    # self.set 2, *
    def set2b(self):
        self.regB |= 0x04
    
    def set2c(self):
        self.regC |= 0x04
    
    def set2d(self):
        self.regD |= 0x04
    
    def set2e(self):
        self.regE |= 0x04
    
    def set2h(self):
        self.regH |= 0x04
    
    def set2l(self):
        self.regL |= 0x04
    
    def set2fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x04
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set2a(self):
        self.regA |= 0x04
    
    # self.set 3, *
    def set3b(self):
        self.regB |= 0x08
    
    def set3c(self):
        self.regC |= 0x08
    
    def set3d(self):
        self.regD |= 0x08
    
    def set3e(self):
        self.regE |= 0x08
    
    def set3h(self):
        self.regH |= 0x08
    
    def set3l(self):
        self.regL |= 0x08
    
    def set3fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x08
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set3a(self):
        self.regA |= 0x08
    
    # self.set 4, *
    def set4b(self):
        self.regB |= 0x10
    
    def set4c(self):
        self.regC |= 0x10
    
    def set4d(self):
        self.regD |= 0x10
    
    def set4e(self):
        self.regE |= 0x10
    
    def set4h(self):
        self.regH |= 0x10
    
    def set4l(self):
        self.regL |= 0x10
    
    def set4fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x10
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set4a(self):
        self.regA |= 0x10
    
    # self.set 5, *
    def set5b(self):
        self.regB |= 0x20
    
    def set5c(self):
        self.regC |= 0x20
    
    def set5d(self):
        self.regD |= 0x20
    
    def set5e(self):
        self.regE |= 0x20
    
    def set5h(self):
        self.regH |= 0x20
    
    def set5l(self):
        self.regL |= 0x20
    
    def set5fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x20
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set5a(self):
        self.regA |= 0x20
    
    # self.set 6, *
    def set6b(self):
        self.regB |= 0x40
    
    def set6c(self):
        self.regC |= 0x40
    
    def set6d(self):
        self.regD |= 0x40
    
    def set6e(self):
        self.regE |= 0x40
    
    def set6h(self):
        self.regH |= 0x40
    
    def set6l(self):
        self.regL |= 0x40
    
    def set6fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x40
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set6a(self):
        self.regA |= 0x40
    
    # self.set 7, *
    def set7b(self):
        self.regB |= 0x80
    
    def set7c(self):
        self.regC |= 0x80
    
    def set7d(self):
        self.regD |= 0x80
    
    def set7e(self):
        self.regE |= 0x80
    
    def set7h(self):
        self.regH |= 0x80
    
    def set7l(self):
        self.regL |= 0x80
    
    def set7fromhl(self):
        work16 = self.get_reg_HL()
        work8 = self.bus_access.peekb(work16) | 0x80
        self.bus_access.address_on_bus(work16, 1)
        self.bus_access.pokeb(work16, work8)
    
    def set7a(self):
        self.regA |= 0x80
    
    def cb(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        self._cbdict[opcode]()

    def outna(self):
        work8 = self.bus_access.peekb(self.regPC)
        self.memptr = self.regA << 8
        self.bus_access.out_port(self.memptr | work8, self.regA)
        self.memptr |= ((work8 + 1) & 0xff)
        self.regPC = (self.regPC + 1) & 0xffff
    
    def inan(self):
        self.memptr = (self.regA << 8) | self.bus_access.peekb(self.regPC)
        self.regA = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 1) & 0xffff
    
    def exsphl(self):
        work16 = self.regH
        work8 = self.regL
        self.set_reg_HL(self.bus_access.peekw(self.regSP))
        self.bus_access.address_on_bus((self.regSP + 1) & 0xffff, 1)
        self.bus_access.pokeb((self.regSP + 1) & 0xffff, work16)
        self.bus_access.pokeb(self.regSP, work8)
        self.bus_access.address_on_bus(self.regSP, 2)
        self.memptr = self.get_reg_HL()
    
    def exdehl(self):
        work8 = self.regH
        self.regH = self.regD
        self.regD = work8

        work8 = self.regL
        self.regL = self.regE
        self.regE = work8
    
    def di(self):
        self.ffIFF1 = False
        self.ffIFF2 = False

    def ei(self):
        self.ffIFF1 = self.ffIFF2 = True
        self.pendingEI = True
    
    # CALL cc,nn
    def callnznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callznn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & ZERO_MASK) != 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callncnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if not self.carryFlag:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callcnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.carryFlag:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callponn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & PARITY_MASK) == 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callpenn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if (self.sz5h3pnFlags & PARITY_MASK) != 0:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callpnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.sz5h3pnFlags < SIGN_MASK:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    def callmnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        if self.sz5h3pnFlags > 0x7f:
            self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
            self.push(self.regPC + 2)
            self.regPC = self.memptr
        else:
            self.regPC = (self.regPC + 2) & 0xffff
    
    # PUSH
    def pushbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.get_reg_BC())
    
    def pushde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.get_reg_DE())
    
    def pushhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.get_reg_HL())
    
    def pushaf(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.get_reg_AF())
    
    # op A,N
    def addan(self):
        self.add(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def adcan(self):
        self.adc(self.bus_access.peekw(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def suban(self):
        self.sub(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def sbcan(self):
        self.sbc(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def andan(self):
        self._and(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def xoran(self):
        self._xor(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def oran(self):
        self._or(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def cpan(self):
        self.cp(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    # RST n
    def rst0(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x00
    
    def rst8(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x08
    
    def rst16(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x10
    
    def rst24(self):
        self.sbc(self.bus_access.peekb(self.regPC))
        self.regPC = (self.regPC + 1) & 0xffff
    
    def rst32(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x20
    
    def rst40(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x28
    
    def rst48(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x30
    
    def rst56(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(self.regPC)
        self.regPC = self.memptr = 0x38
    
    # Various
    def callnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.address_on_bus((self.regPC + 1) & 0xffff, 1)
        self.push(self.regPC + 2)
        self.regPC = self.memptr
    
    def ix(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._ixiydict.get(opcode)
        if code is None:
            self.main_cmds[opcode]()
        else:
            self.regIX = code(self.regIX)

    # ED prefix
    # IN r,(c)
    def inbfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regB = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regB]
        self.flagQ = True
    
    def incfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regC = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regC]
        self.flagQ = True

    def indfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regD = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regD]
        self.flagQ = True
    
    def inefrombc(self):
        self.memptr = self.get_reg_BC()
        self.regE = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regE]
        self.flagQ = True
    
    def inhfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regH = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regH]
        self.flagQ = True

    def inlfrombc(self):
        self.memptr = self.get_reg_BC()
        self.regL = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regL]
        self.flagQ = True
    
    def infrombc(self):
        self.memptr = self.get_reg_BC()
        in_port = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[in_port]
        self.flagQ = True

    def inafrombc(self):
        self.memptr = self.get_reg_BC()
        self.regA = self.bus_access.in_port(self.memptr)
        self.memptr += 1
        self.sz5h3pnFlags = self.sz53pn_addTable[self.regA]
        self.flagQ = True

    # OUT (c),r
    def outtocb(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regB)
        self.memptr += 1
    
    def outtocc(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regC)
        self.memptr += 1
    
    def outtocd(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regD)
        self.memptr += 1
    
    def outtoce(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regE)
        self.memptr += 1
    
    def outtoch(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regH)
        self.memptr += 1
    
    def outtocl(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regL)
        self.memptr += 1
    
    def outtoc0(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, 0)
        self.memptr += 1
    
    def outtoca(self):
        self.memptr = self.get_reg_BC()
        self.bus_access.out_port(self.memptr, self.regA)
        self.memptr += 1
    
    # SBC/ADC HL,ss
    def sbchlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.sbc16(self.get_reg_BC())
    
    def adchlbc(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.adc16(self.get_reg_BC())
    
    def sbchlde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.sbc16(self.get_reg_DE())
    
    def adchlde(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.adc16(self.get_reg_DE())
    
    def sbchlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.sbc16(self.get_reg_HL())
    
    def adchlhl(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.adc16(self.get_reg_HL())
    
    def sbchlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.sbc16(self.regSP)
    
    def adchlsp(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        self.adc16(self.regSP)
    
    # LD (nn),ss, LD ss,(nn)
    def ldtonnbc(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_BC())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def ldbcfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_BC(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def ldtonnde(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_DE())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def lddefromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_DE(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def edldtonnhl(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.get_reg_HL())
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def edldhlfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.set_reg_HL(self.bus_access.peekw(self.memptr))
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    def ldtonnsp(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.regSP)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
    
    def ldspfromnn(self):
        self.memptr = self.bus_access.peekw(self.regPC)
        self.regSP = self.bus_access.peekw(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff

    # NEG
    def nega(self):
        aux = self.regA
        self.regA = 0
        self.sub(aux)
    
    # RETn
    def retn(self):
        self.ffIFF1 = self.ffIFF2
        self.regPC = self.memptr = self.pop()
    
    def reti(self):
        self.ffIFF1 = self.ffIFF2
        self.regPC = self.memptr = self.pop()
    
    # IM x
    def im0(self):
        self.modeINT = IM0
    
    def im1(self):
        self.modeINT = IM1
    
    def im2(self):
        self.modeINT = IM2
    
    # LD A,s / LD s,A / RxD
    def ldia(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regI = self.regA
    
    def ldra(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.set_reg_R(self.regA)
    
    def ldai(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regA = self.regI
        self.sz5h3pnFlags = self.sz53n_addTable[self.regA]
        if self.ffIFF2 and not self.bus_access.is_active_INT():
            self.sz5h3pnFlags |= PARITY_MASK
        self.flagQ = True
    
    # Load a with r - (NOT CHECKED)
    def ldar(self):
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.regA = self.get_reg_R()
        self.sz5h3pnFlags = self.sz53n_addTable[self.regA]
        if self.ffIFF2 and not self.bus_access.is_active_INT():
            self.sz5h3pnFlags |= PARITY_MASK
        self.flagQ = True
    
    def rrda(self):
        self.rrd()
    
    def rlda(self):
        self.rld()

    # xxIR
    def ldir(self):
        self.ldi()
        if (self.sz5h3pnFlags & PARITY_MASK) == PARITY_MASK:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_DE() - 1) & 0xffff, 5)
            self.sz5h3pnFlags &= ~FLAG_53_MASK
            self.sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)

    def cpir(self):
        self.cpi()
        if (self.sz5h3pnFlags & PARITY_MASK) == PARITY_MASK and (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_HL() - 1) & 0xffff, 5)
            self.sz5h3pnFlags &= ~FLAG_53_MASK
            self.sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def inir(self):
        self.ini()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus((self.get_reg_HL() - 1) & 0xffff, 5)
            self.adjustINxROUTxRFlags()
    
    def otir(self):
        self.outi()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus(self.get_reg_BC(), 5)
            self.adjustINxROUTxRFlags()
    
    # xxDR
    def lddr(self):
        self.ldd()
        if (self.sz5h3pnFlags & PARITY_MASK) == PARITY_MASK:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_DE() + 1) & 0xffff, 5)
            self.sz5h3pnFlags &= ~FLAG_53_MASK
            self.sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def cpdr(self):
        self.cpd()
        if (self.sz5h3pnFlags & PARITY_MASK) == PARITY_MASK and (self.sz5h3pnFlags & ZERO_MASK) == 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.memptr = self.regPC + 1
            self.bus_access.address_on_bus((self.get_reg_HL() + 1) & 0xffff, 5)
            self.sz5h3pnFlags &= ~FLAG_53_MASK
            self.sz5h3pnFlags |= ((self.regPC >> 8) & FLAG_53_MASK)
    
    def indr(self):
        self.ind()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus((self.get_reg_HL() + 1) & 0xffff, 5)
            self.adjustINxROUTxRFlags()
    
    def otdr(self):
        self.outd()
        if self.regB != 0:
            self.regPC = (self.regPC - 2) & 0xffff
            self.bus_access.address_on_bus(self.get_reg_BC(), 5)
            self.adjustINxROUTxRFlags()

    def opcodedd(self):
        self.prefixOpcode = 0xDD

    def opcodeed(self):
        self.prefixOpcode = 0xED

    def opcodefd(self):
        self.prefixOpcode = 0xFD

    @staticmethod
    def ednop():
        return 8
    
    def ed(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._eddict.get(opcode)
        if code is not None:
            code()

    def iy(self):
        opcode = self.bus_access.fetch_opcode(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        self.regR += 1
        code = self._ixiydict.get(opcode)
        if code is None:
            self.main_cmds[opcode]()
        else:
            self.regIY = code(self.regIY)

    # IX, IY ops ---------------------------
    # ADD ID, *
    def addidbc(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self.add16(regIXY, self.get_reg_BC())
    
    def addidde(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self.add16(regIXY, self.get_reg_DE())
    
    def addidid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self.add16(regIXY, regIXY)

    def addidsp(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 7)
        return self.add16(regIXY, self.regSP)
    
    # LD ID, nn
    def ldidnn(self, _regIXY: int) -> int:
        regIXY = self.bus_access.peekw(self.regPC)
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    def ldtonnid(self, regIXY: int) -> int:
        self.memptr = self.bus_access.peekw(self.regPC)
        self.bus_access.pokew(self.memptr, self.regPC)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    def ldidfromnn(self, _regIXY: int) -> int:
        self.memptr = self.bus_access.peekw(self.regPC)
        regIXY = self.bus_access.peekw(self.memptr)
        self.memptr += 1
        self.regPC = (self.regPC + 2) & 0xffff
        return regIXY
    
    # INC
    def incid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        return (regIXY + 1) & 0xffff
    
    def incidh(self, regIXY: int) -> int:
        return (self.inc8(regIXY >> 8) << 8) | (regIXY & 0xff)
    
    def incidl(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.inc8(regIXY & 0xff)
    
    def incinidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        work8 = self.bus_access.peekb(self.memptr)
        self.bus_access.address_on_bus(self.memptr, 1)
        self.bus_access.pokeb(self.memptr, self.inc8(work8))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # DEC
    def decid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        return (regIXY - 1) & 0xffff
    
    def decidh(self, regIXY: int) -> int:
        return (self.dec8(regIXY >> 8) << 8) | (regIXY & 0xff)
    
    def decidl(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.dec8(regIXY & 0xff)
    
    def decinidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        work8 = self.bus_access.peekb(self.memptr)
        self.bus_access.address_on_bus(self.memptr, 1)
        self.bus_access.pokeb(self.memptr, self.dec8(work8))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # LD *, IDH
    def ldbidh(self, regIXY: int) -> int:
        self.regB = regIXY >> 8
        return regIXY
    
    def ldcidh(self, regIXY: int) -> int:
        self.regC = regIXY >> 8
        return regIXY
    
    def lddidh(self, regIXY: int) -> int:
        self.regD = regIXY >> 8
        return regIXY
    
    def ldeidh(self, regIXY: int) -> int:
        self.regE = regIXY >> 8
        return regIXY
    
    @staticmethod
    def ldaidh(regIXY: int) -> int:
        return regIXY >> 8
    
    # LD *, IDL
    def ldbidl(self, regIXY: int) -> int:
        self.regB = regIXY & 0xff
        return regIXY
    
    def ldcidl(self, regIXY: int) -> int:
        self.regC = regIXY & 0xff
        return regIXY
    
    def lddidl(self, regIXY: int) -> int:
        self.regD = regIXY & 0xff
        return regIXY
    
    def ldeidl(self, regIXY: int) -> int:
        self.regE = regIXY & 0xff
        return regIXY
    
    @staticmethod
    def ldaidl(regIXY: int) -> int:
        return regIXY & 0xff
    
    # LD IDH, *
    def ldidhb(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regB << 8)
    
    def ldidhc(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regC << 8)

    def ldidhd(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regD << 8)
    
    def ldidhe(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regE << 8)
    
    @staticmethod
    def ldidhidh(regIXY: int) -> int:
        return regIXY
    
    @staticmethod
    def ldidhidl(regIXY: int) -> int:
        return (regIXY & 0x00ff) | ((regIXY & 0xff) << 8)
    
    def ldidhn(self, regIXY: int) -> int:
        regIXY = (self.bus_access.peekb(self.regPC) << 8) | (regIXY & 0xff)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldidha(self, regIXY: int) -> int:
        return (regIXY & 0x00ff) | (self.regA << 8)
    
    # LD IDL, *
    def ldidlb(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regB
    
    def ldidlc(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regC
    
    def ldidld(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regD
    
    def ldidle(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regE
    
    @staticmethod
    def ldidlidh(regIXY: int) -> int:
        return (regIXY & 0xff00) | (regIXY >> 8)
    
    @staticmethod
    def ldidlidl(regIXY: int) -> int:
        return regIXY
    
    def ldidln(self, regIXY: int) -> int:
        regIXY = (regIXY & 0xff00) | self.bus_access.peekb(self.regPC)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def ldidla(self, regIXY: int) -> int:
        return (regIXY & 0xff00) | self.regA
    
    # LD *, (ID+d)
    def ldbfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regB = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def ldcfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regC = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def lddfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regD = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldefromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regE = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldhfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regH = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldlfromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regL = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def ldafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.regA = self.bus_access.peekb(self.memptr)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # LD (ID+d), *
    def ldtoiddb(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regB)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoiddc(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regC)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoiddd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regD)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoidde(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regE)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoiddh(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regH)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoiddl(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regL)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def ldtoiddn(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.regPC = (self.regPC + 1) & 0xffff
        work8 = self.bus_access.peekb(self.regPC)
        self.bus_access.address_on_bus(self.regPC, 2)
        self.regPC = (self.regPC + 1) & 0xffff
        self.bus_access.pokeb(self.memptr, work8)
        return regIXY
    
    def ldtoidda(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.bus_access.pokeb(self.memptr, self.regA)
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # ADD/ADC A, *
    def addaidh(self, regIXY: int) -> int:
        self.add(regIXY >> 8)
        return regIXY
    
    def addaidl(self, regIXY: int) -> int:
        self.add(regIXY & 0xff)
        return regIXY
    
    def addafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.add(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def adcaidh(self, regIXY: int) -> int:
        self.adc(regIXY >> 8)
        return regIXY
    
    def adcaidl(self, regIXY: int) -> int:
        self.adc(regIXY & 0xff)
        return regIXY
    
    def adcafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.adc(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # SUB/SBC A, *
    def subaidh(self, regIXY: int) -> int:
        self.sub(regIXY >> 8)
        return regIXY

    def subaidl(self, regIXY: int) -> int:
        self.sub(regIXY & 0xff)
        return regIXY

    def subafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.sub(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def sbcaidh(self, regIXY: int) -> int:
        self.sbc(regIXY >> 8)
        return regIXY
    
    def sbcaidl(self, regIXY: int) -> int:
        self.sbc(regIXY & 0xff)
        return regIXY
    
    def sbcafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.sbc(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # Bitwise OPS
    def andaidh(self, regIXY: int) -> int:
        self._and(regIXY >> 8)
        return regIXY
    
    def andaidl(self, regIXY: int) -> int:
        self._and(regIXY & 0xff)
        return regIXY
    
    def andafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._and(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    def xoraidh(self, regIXY: int) -> int:
        self._xor(regIXY >> 8)
        return regIXY

    def xoraidl(self, regIXY: int) -> int:
        self._xor(regIXY & 0xff)
        return regIXY

    def xorafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._xor(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    def oraidh(self, regIXY: int) -> int:
        self._or(regIXY >> 8)
        return regIXY

    def oraidl(self, regIXY: int) -> int:
        self._or(regIXY & 0xff)
        return regIXY

    def orafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self._or(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY

    # CP A, *
    def cpaidh(self, regIXY: int) -> int:
        self.cp(regIXY >> 8)
        return regIXY

    def cpaidl(self, regIXY: int) -> int:
        self.cp(regIXY & 0xff)
        return regIXY

    def cpafromidd(self, regIXY: int) -> int:
        self.memptr = (regIXY + self.bus_access.peeksb(self.regPC)) & 0xffff
        self.bus_access.address_on_bus(self.regPC, 5)
        self.cp(self.bus_access.peekb(self.memptr))
        self.regPC = (self.regPC + 1) & 0xffff
        return regIXY
    
    # Various
    def pushid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 1)
        self.push(regIXY)
        return regIXY

    def popid(self, _regIXY: int) -> int:
        return self.pop()
    
    def jpid(self, regIXY: int) -> int:
        self.regPC = regIXY
        return regIXY
    
    def ldspid(self, regIXY: int) -> int:
        self.bus_access.address_on_bus(self.get_pair_IR(), 2)
        self.regSP = regIXY
        return regIXY
    
    def exfromspid(self, regIXY: int) -> int:
        work16 = regIXY
        regIXY = self.bus_access.peekw(self.regSP)
        self.bus_access.address_on_bus((self.regSP + 1) & 0xffff, 1)
        self.bus_access.pokeb((self.regSP + 1) & 0xffff, work16 >> 8)
        self.bus_access.pokeb(self.regSP, work16)
        self.bus_access.address_on_bus(self.regSP, 2)
        self.memptr = regIXY
        return regIXY

    def opcodedd_ixy(self, regIXY: int) -> int:
        self.prefixOpcode = 0xDD
        return regIXY

    def opcodeed_ixy(self, regIXY: int) -> int:
        self.prefixOpcode = 0xED
        return regIXY

    def opcodefd_ixy(self, regIXY: int) -> int:
        self.prefixOpcode = 0xFD
        return regIXY

    def idcb(self, regIXY: int) -> int:
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
    def cbrlcb(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8

    def cbrlcc(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbrlcd(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbrlce(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbrlch(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbrlcl(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbrlcinhl(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbrlca(self, address):
        work8 = self.rlc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rrc *
    def cbrrcb(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbrrcc(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbrrcd(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbrrce(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbrrch(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbrrcl(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbrrcinhl(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbrrca(self, address):
        work8 = self.rrc(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rl *
    def cbrlb(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbrlc(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbrld(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbrle(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbrlh(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbrll(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbrlinhl(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbrla(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.rr *
    def cbrrb(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbrrc(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbrrd(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbrre(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbrrh(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbrrl(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbrrinhl(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbrra(self, address):
        work8 = self.rl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sla *
    def cbslab(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbslac(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbslad(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8

    def cbslae(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbslah(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbslal(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbslainhl(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbslaa(self, address):
        work8 = self.sla(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sra *
    def cbsrab(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbsrac(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbsrad(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbsrae(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbsrah(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbsral(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbsrainhl(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbsraa(self, address):
        work8 = self.sra(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.sls *
    def cbslsb(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbslsc(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbslsd(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbslse(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbslsh(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbslsl(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbslsinhl(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbslsa(self, address):
        work8 = self.sll(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.srl *
    def cbsrlb(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbsrlc(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbsrld(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbsrle(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbsrlh(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbsrll(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbsrlinhl(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbsrla(self, address):
        work8 = self.srl(self.bus_access.peekb(address))
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8

    # self.bit *
    def cbbit0(self, address):
        self.bit(0x01, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit1(self, address):
        self.bit(0x02, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit2(self, address):
        self.bit(0x04, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit3(self, address):
        self.bit(0x08, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit4(self, address):
        self.bit(0x10, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit5(self, address):
        self.bit(0x20, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit6(self, address):
        self.bit(0x40, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    def cbbit7(self, address):
        self.bit(0x80, self.bus_access.peekb(address))
        self.sz5h3pnFlags = (self.sz5h3pnFlags & FLAG_SZHP_MASK) | ((address >> 8) & FLAG_53_MASK)
        self.bus_access.address_on_bus(address, 1)
    
    # self.res 0, *
    def cbres0b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8

    def cbres0c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres0d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres0e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres0h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres0l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres0inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres0a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFE
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 1, *
    def cbres1b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres1c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres1d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres1e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres1h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres1l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres1inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres1a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFD
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 2, *
    def cbres2b(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres2c(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres2d(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres2e(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres2h(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres2l(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres2inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres2a(self, address):
        work8 = self.bus_access.peekb(address) & 0xFB
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 3, *
    def cbres3b(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres3c(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres3d(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres3e(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres3h(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres3l(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres3inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres3a(self, address):
        work8 = self.bus_access.peekb(address) & 0xF7
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 4, *
    def cbres4b(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres4c(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres4d(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres4e(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres4h(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres4l(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres4inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres4a(self, address):
        work8 = self.bus_access.peekb(address) & 0xEF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 5, *
    def cbres5b(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres5c(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres5d(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres5e(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres5h(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres5l(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres5inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres5a(self, address):
        work8 = self.bus_access.peekb(address) & 0xDF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 6, *
    def cbres6b(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres6c(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres6d(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres6e(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres6h(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres6l(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres6inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres6a(self, address):
        work8 = self.bus_access.peekb(address) & 0xBF
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.res 7, *
    def cbres7b(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbres7c(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbres7d(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbres7e(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbres7h(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbres7l(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbres7inhl(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbres7a(self, address):
        work8 = self.bus_access.peekb(address) & 0x7F
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 0, *
    def cbset0b(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset0c(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset0d(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset0e(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset0h(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset0l(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset0inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset0a(self, address):
        work8 = self.bus_access.peekb(address) | 0x01
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 1, *
    def cbset1b(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset1c(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset1d(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset1e(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset1h(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset1l(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset1inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset1a(self, address):
        work8 = self.bus_access.peekb(address) | 0x02
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 2, *
    def cbset2b(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset2c(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset2d(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset2e(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset2h(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset2l(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset2inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset2a(self, address):
        work8 = self.bus_access.peekb(address) | 0x04
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 3, *
    def cbset3b(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset3c(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset3d(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset3e(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset3h(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8

    def cbset3l(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset3inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset3a(self, address):
        work8 = self.bus_access.peekb(address) | 0x08
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 4, *
    def cbset4b(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset4c(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset4d(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset4e(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset4h(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset4l(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset4inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset4a(self, address):
        work8 = self.bus_access.peekb(address) | 0x10
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 5, *
    def cbset5b(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset5c(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset5d(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset5e(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset5h(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset5l(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset5inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset5a(self, address):
        work8 = self.bus_access.peekb(address) | 0x20
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 6, *
    def cbset6b(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset6c(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset6d(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset6e(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset6h(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset6l(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset6inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset6a(self, address):
        work8 = self.bus_access.peekb(address) | 0x40
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
    
    # self.set 7, *
    def cbset7b(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regB = work8
    
    def cbset7c(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regC = work8
    
    def cbset7d(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regD = work8
    
    def cbset7e(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regE = work8
    
    def cbset7h(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regH = work8
    
    def cbset7l(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regL = work8
    
    def cbset7inhl(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)

    def cbset7a(self, address):
        work8 = self.bus_access.peekb(address) | 0x80
        self.bus_access.address_on_bus(address, 1)
        self.bus_access.pokeb(address, work8)
        self.regA = work8
