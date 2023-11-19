from typing import Callable

from memory import Memory
from ports import Ports

IM0 = 0
IM1 = 1
IM2 = 2

F_C = 0x01
F_N = 0x02
F_PV = 0x04
F_3 = 0x08
F_H = 0x10
F_5 = 0x20
F_Z = 0x40
F_S = 0x80
F_3_16 = F_3 << 8
F_5_16 = F_5 << 8

PF = F_PV


class Z80:
    def __init__(self, memory: Memory, ports: Ports, clock_cycle_test: Callable[['Z80'], None], clock_frequency_in_MHz: float = 3.5) -> None:
        self.memory = memory
        self.ports = ports
        self.clock_cycle_test = clock_cycle_test
        self.video_update_time = 0

        self.show_debug_info = False
        self.tstates_per_interrupt = int((clock_frequency_in_MHz * 1000000.0) / 50)
        self.local_clock_cycles_counter = -self.tstates_per_interrupt  # -70000

        self.p_ = 0
        self.parity = [False] * 256
        for i in range(256):
            p = True
            int_type = i
            while int_type:
                p = not self.p_
                int_type = int_type & (int_type - 1)
            self.parity[i] = p

        # **Main registers
        self._AF_b = bytearray(2)
        self._A_F = memoryview(self._AF_b)
        self._F = self._A_F[0:1]
        self._A = self._A_F[1:2]
        self._AF = self._A_F.cast('H')
        self._fS = False
        self._fZ = False
        self._fZ = False
        self._fH = False
        self._f3 = False
        self._f5 = False
        self._fPV = False
        self._fN = False
        self._fC = False

        self._HL_b = bytearray(2)
        self._H_L = memoryview(self._HL_b)
        self._L = self._H_L[0:1]
        self._H = self._H_L[1:2]
        self._HL = self._H_L.cast('H')
        
        self._BC_b = bytearray(2)
        self._B_C = memoryview(self._BC_b)
        self._C = self._B_C[0:1]
        self._B = self._B_C[1:2]
        self._BC = self._B_C.cast('H')
        
        self._DE_b = bytearray(2)
        self._D_E = memoryview(self._DE_b)
        self._E = self._D_E[0:1]
        self._D = self._D_E[1:2]
        self._DE = self._D_E.cast('H')
        
        # ** Alternate registers
        self._AF_b_ = bytearray(2)
        self._A_F_ = memoryview(self._AF_b_)
        self._F_ = self._A_F_[0:1]
        self._A_ = self._A_F_[1:2]
        self._AF_ = self._A_F_.cast('H')
        
        self._HL_b_ = bytearray(2)
        self._H_L_ = memoryview(self._HL_b_)
        self._L_ = self._H_L_[0:1]
        self._H_ = self._H_L_[1:2]
        self._HL_ = self._H_L_.cast('H')
        
        self._BC_b_ = bytearray(2)
        self._B_C_ = memoryview(self._BC_b_)
        self._C_ = self._B_C_[0:1]
        self._B_ = self._B_C_[1:2]
        self._BC_ = self._B_C_.cast('H')
        
        self._DE_b_ = bytearray(2)
        self._D_E_ = memoryview(self._DE_b_)
        self._E_ = self._D_E_[0:1]
        self._D_ = self._D_E_[1:2]
        self._DE_ = self._D_E_.cast('H')
        
        # ** Index registers - ID used as temporary for ix/iy
        self._IX_b = bytearray(2)
        self._IXH_IXL = memoryview(self._IX_b)
        self._IXL = self._IXH_IXL[0:1]
        self._IXH = self._IXH_IXL[1:2]
        self._IX = self._IXH_IXL.cast('H')
        
        self._IY_b = bytearray(2)
        self._IYH_IYL = memoryview(self._IY_b)
        self._IYL = self._IYH_IYL[0:1]
        self._IYH = self._IYH_IYL[1:2]
        self._IY = self._IYH_IYL.cast('H')
        
        self._IDH = None
        self._IDL = None
        self._ID = None
        
        # ** Stack Pointer and Program Counter
        self._SP_b = bytearray(2)
        self._SP = memoryview(self._SP_b).cast('H')
        
        self._PC_b = bytearray(2)
        self._PC = memoryview(self._PC_b).cast('H')
        
        # ** Interrupt and Refresh registers
        self._I_b = bytearray(2)
        self._IH_IL = memoryview(self._I_b)
        self._I = self._IH_IL[1:2]
        # _Ifull = self._IH_IL.cast('H')
        
        # self.memory refresh register
        self._R_b = self._IH_IL[0:1]
        self._R7_b = 0
        
        def _Rget():
            return self._R_b[0]
        
        def _Rset(r):
            self._R_b[0] = r
            self._R7_b = 0x80 if r > 0x7F else 0
        self._R = property(_Rget, _Rset)

        # ** Interrupt flip-flops
        self._IFF1 = True
        self._IFF2 = True
        self._IM = IM2

        self._cbdict = {
            0: self.rlcb, 1: self.rlcc, 2: self.rlcd, 3: self.rlce, 4: self.rlch, 5: self.rlcl, 6: self.rlcfromhl, 7: self.rlc_a,
            8: self.rrcb, 9: self.rrcc, 10: self.rrcd, 11: self.rrce, 12: self.rrch, 13: self.rrcl, 14: self.rrcfromhl, 15: self.rrc_a,
            16: self.rlb, 17: self.rl_c, 18: self.rld, 19: self.rle, 20: self.rlh, 21: self.rll, 22: self.rlfromhl, 23: self.rl_a,
            24: self.rrb, 25: self.rr_c, 26: self.rrd, 27: self.rre, 28: self.rrh, 29: self.rrl, 30: self.rrfromhl, 31: self.rr_a,
            32: self.slab, 33: self.slac, 34: self.slad, 35: self.slae, 36: self.slah, 37: self.slal, 38: self.slafromhl, 39: self.sla_a,
            40: self.srab, 41: self.srac, 42: self.srad, 43: self.srae, 44: self.srah, 45: self.sral, 46: self.srafromhl, 47: self.sra_a,
            48: self.slsb, 49: self.slsc, 50: self.slsd, 51: self.slse, 52: self.slsh, 53: self.slsl, 54: self.slsfromhl, 55: self.sls_a,
            56: self.srlb, 57: self.srlc, 58: self.srld, 59: self.srle, 60: self.srlh, 61: self.srll, 62: self.srlfromhl, 63: self.srl_a,
        
            64: self.bit0b, 65: self.bit0c, 66: self.bit0d, 67: self.bit0e, 68: self.bit0h, 69: self.bit0l, 70: self.bit0fromhl, 71: self.bit0a,
            72: self.bit1b, 73: self.bit1c, 74: self.bit1d, 75: self.bit1e, 76: self.bit1h, 77: self.bit1l, 78: self.bit1fromhl, 79: self.bit1a,
            80: self.bit2b, 81: self.bit2c, 82: self.bit2d, 83: self.bit2e, 84: self.bit2h, 85: self.bit2l, 86: self.bit2fromhl, 87: self.bit2a,
            88: self.bit3b, 89: self.bit3c, 90: self.bit3d, 91: self.bit3e, 92: self.bit3h, 93: self.bit3l, 94: self.bit3fromhl, 95: self.bit3a,
            96: self.bit4b, 97: self.bit4c, 98: self.bit4d, 99: self.bit4e, 100: self.bit4h, 101: self.bit4l, 102: self.bit4fromhl, 103: self.bit4a,
            104: self.bit5b, 105: self.bit5c, 106: self.bit5d, 107: self.bit5e, 108: self.bit5h, 109: self.bit5l, 110: self.bit5fromhl, 111: self.bit5a,
            112: self.bit6b, 113: self.bit6c, 114: self.bit6d, 115: self.bit6e, 116: self.bit6h, 117: self.bit6l, 118: self.bit6fromhl, 119: self.bit6a,
            120: self.bit7b, 121: self.bit7c, 122: self.bit7d, 123: self.bit7e, 124: self.bit7h, 125: self.bit7l, 126: self.bit7fromhl, 127: self.bit7a,
        
            128: self.res0b, 129: self.res0c, 130: self.res0d, 131: self.res0e, 132: self.res0h, 133: self.res0l, 134: self.res0fromhl, 135: self.res0a,
            136: self.res1b, 137: self.res1c, 138: self.res1d, 139: self.res1e, 140: self.res1h, 141: self.res1l, 142: self.res1fromhl, 143: self.res1a,
            144: self.res2b, 145: self.res2c, 146: self.res2d, 147: self.res2e, 148: self.res2h, 149: self.res2l, 150: self.res2fromhl, 151: self.res2a,
            152: self.res3b, 153: self.res3c, 154: self.res3d, 155: self.res3e, 156: self.res3h, 157: self.res3l, 158: self.res3fromhl, 159: self.res3a,
            160: self.res4b, 161: self.res4c, 162: self.res4d, 163: self.res4e, 164: self.res4h, 165: self.res4l, 166: self.res4fromhl, 167: self.res4a,
            168: self.res5b, 169: self.res5c, 170: self.res5d, 171: self.res5e, 172: self.res5h, 173: self.res5l, 174: self.res5fromhl, 175: self.res5a,
            176: self.res6b, 177: self.res6c, 178: self.res6d, 179: self.res6e, 180: self.res6h, 181: self.res6l, 182: self.res6fromhl, 183: self.res6a,
            184: self.res7b, 185: self.res7c, 186: self.res7d, 187: self.res7e, 188: self.res7h, 189: self.res7l, 190: self.res7fromhl, 191: self.res7a,
        
            192: self.set0b, 193: self.set0c, 194: self.set0d, 195: self.set0e, 196: self.set0h, 197: self.set0l, 198: self.set0fromhl, 199: self.set0a,
            200: self.set1b, 201: self.set1c, 202: self.set1d, 203: self.set1e, 204: self.set1h, 205: self.set1l, 206: self.set1fromhl, 207: self.set1a,
            208: self.set2b, 209: self.set2c, 210: self.set2d, 211: self.set2e, 212: self.set2h, 213: self.set2l, 214: self.set2fromhl, 215: self.set2a,
            216: self.set3b, 217: self.set3c, 218: self.set3d, 219: self.set3e, 220: self.set3h, 221: self.set3l, 222: self.set3fromhl, 223: self.set3a,
            224: self.set4b, 225: self.set4c, 226: self.set4d, 227: self.set4e, 228: self.set4h, 229: self.set4l, 230: self.set4fromhl, 231: self.set4a,
            232: self.set5b, 233: self.set5c, 234: self.set5d, 235: self.set5e, 236: self.set5h, 237: self.set5l, 238: self.set5fromhl, 239: self.set5a,
            240: self.set6b, 241: self.set6c, 242: self.set6d, 243: self.set6e, 244: self.set6h, 245: self.set6l, 246: self.set6fromhl, 247: self.set6a,
            248: self.set7b, 249: self.set7c, 250: self.set7d, 251: self.set7e, 252: self.set7h, 253: self.set7l, 254: self.set7fromhl, 255: self.set7a
        }

        self._eddict = {
            64: self.inbfrombc, 72: self.incfrombc, 80: self.indfrombc, 88: self.inefrombc, 96: self.inhfrombc, 104: self.inlfrombc, 112: self.infrombc, 120: self.inafrombc,
            65: self.outtocb, 73: self.outtocc, 81: self.outtocd, 89: self.outtoce, 97: self.outtoch, 105: self.outtocl, 113: self.outtoc0, 121: self.outtoca,
            66: self.sbchlbc, 74: self.adchlbc, 82: self.sbchlde, 90: self.adchlde, 98: self.sbchlhl, 106: self.adchlhl, 114: self.sbchlsp, 122: self.adchlsp,
            67: self.ldtonnbc, 75: self.ldbcfromnn, 83: self.ldtonnde, 91: self.lddefromnn, 99: self.edldtonnhl, 107: self.edldhlfromnn, 115: self.ldtonnsp, 123: self.ldspfromnn,
            68: self.nega, 76: self.nega, 84: self.nega, 92: self.nega, 100: self.nega, 108: self.nega, 116: self.nega, 124: self.nega,
            69: self.retn, 85: self.retn, 101: self.retn, 117: self.retn, 77: self.reti, 93: self.reti, 109: self.reti, 125: self.reti,
            70: self.im0, 78: self.im0, 102: self.im0, 110: self.im0, 86: self.im1, 118: self.im1, 94: self.im2, 126: self.im2,
            71: self.ldia, 79: self.ldra, 87: self.ldai, 95: self.ldar, 103: self.rrda, 111: self.rlda,
            160: self.ldi, 161: self.cpi, 162: self.ini, 163: self.outi,
            168: self.ldd, 169: self.cpd, 170: self.ind, 171: self.outd,
            176: self.ldir, 177: self.cpir, 178: self.inir, 179: self.otir,
            184: self.lddr, 185: self.cpdr, 186: self.indr, 187: self.otdr
        }

        self.main_cmds = {
            0: self.nop, 8: self.ex_af_af, 16: self.djnz, 24: self.jr, 32: self.jrnz, 40: self.jrz, 48: self.jrnc, 56: self.jrc,
            1: self.ldbcnn, 9: self.addhlbc, 17: self.lddenn, 25: self.addhlde, 33: self.ldhlnn, 41: self.addhlhl, 49: self.ldspnn, 57: self.addhlsp,
            2: self.ldtobca, 10: self.ldafrombc, 18: self.ldtodea, 26: self.ldafromde, 34: self.ldtonnhl, 42: self.ldhlfromnn, 50: self.ldtonna, 58: self.ldafromnn,
            3: self.incbc, 11: self.decbc, 19: self.incde, 27: self.decde, 35: self.inchl, 43: self.dechl, 51: self.incsp, 59: self.decsp,
            4: self.incb, 12: self.incc, 20: self.incd, 28: self.ince, 36: self.inch, 44: self.incl, 52: self.incinhl, 60: self.inca,
            5: self.decb, 13: self.decc, 21: self.decd, 29: self.dece, 37: self.dech, 45: self.decl, 53: self.decinhl, 61: self.deca,
            6: self.ldbn, 14: self.ldcn, 22: self.lddn, 30: self.lden, 38: self.ldhn, 46: self.ldln, 54: self.ldtohln, 62: self.ldan,
            7: self.rlca, 15: self.rrca, 23: self.rla, 31: self.rra, 39: self.daa, 47: self.cpla, 55: self.scf, 63: self.ccf,
            64: self.ldbb, 65: self.ldbc, 66: self.ldbd, 67: self.ldbe, 68: self.ldbh, 69: self.ldbl, 70: self.ldbfromhl, 71: self.ldba,
            72: self.ldcb, 73: self.ldcc, 74: self.ldcd, 75: self.ldce, 76: self.ldch, 77: self.ldcl, 78: self.ldcfromhl, 79: self.ldca,
            80: self.lddb, 81: self.lddc, 82: self.lddd, 83: self.ldde, 84: self.lddh, 85: self.lddl, 86: self.lddfromhl, 87: self.ldda,
            88: self.ldeb, 89: self.ldec, 90: self.lded, 91: self.ldee, 92: self.ldeh, 93: self.ldel, 94: self.ldefromhl, 95: self.ldea,
            96: self.ldhb, 97: self.ldhc, 98: self.ldhd, 99: self.ldhe, 100: self.ldhh, 101: self.ldhl, 102: self.ldhfromhl, 103: self.ldha,
            104: self.ldlb, 105: self.ldlc, 106: self.ldld, 107: self.ldle, 108: self.ldlh, 109: self.ldll, 110: self.ldlfromhl, 111: self.ldla,
            112: self.ldtohlb, 113: self.ldtohlc, 114: self.ldtohld, 115: self.ldtohle, 116: self.ldtohlh, 117: self.ldtohll, 119: self.ldtohla,
            120: self.ldab, 121: self.ldac, 122: self.ldad, 123: self.ldae, 124: self.ldah, 125: self.ldal, 126: self.ldafromhl, 127: self.ldaa,
            128: self.addab, 129: self.addac, 130: self.addad, 131: self.addae, 132: self.addah, 133: self.addal, 134: self.addafromhl, 135: self.addaa,
            136: self.adcab, 137: self.adcac, 138: self.adcad, 139: self.adcae, 140: self.adcah, 141: self.adcal, 142: self.adcafromhl, 143: self.adcaa,
            144: self.subab, 145: self.subac, 146: self.subad, 147: self.subae, 148: self.subah, 149: self.subal, 150: self.subafromhl, 151: self.subaa,
            152: self.sbcab, 153: self.sbcac, 154: self.sbcad, 155: self.sbcae, 156: self.sbcah, 157: self.sbcal, 158: self.sbcafromhl, 159: self.sbcaa,
            160: self.andab, 161: self.andac, 162: self.andad, 163: self.andae, 164: self.andah, 165: self.andal, 166: self.andafromhl, 167: self.andaa,
            168: self.xorab, 169: self.xorac, 170: self.xorad, 171: self.xorae, 172: self.xorah, 173: self.xoral, 174: self.xorafromhl, 175: self.xoraa,
            176: self.orab, 177: self.orac, 178: self.orad, 179: self.orae, 180: self.orah, 181: self.oral, 182: self.orafromhl, 183: self.oraa,
            184: self.cpab, 185: self.cpac, 186: self.cpad, 187: self.cpae, 188: self.cpah, 189: self.cpal, 190: self.cpafromhl, 191: self.cpaa,
            192: self.retnz, 200: self.retz, 208: self.retnc, 216: self.retc, 224: self.retpo, 232: self.retpe, 240: self.retp, 248: self.retm,
            193: self.popbc, 209: self.popde, 225: self.pophl, 241: self.popaf,
            194: self.jpnznn, 202: self.jpznn, 210: self.jpncnn, 218: self.jpcnn, 226: self.jpponn, 234: self.jppenn, 242: self.jppnn, 250: self.jpmnn,
            217: self.exx, 233: self.jphl, 249: self.ldsphl, 201: self.ret, 195: self.jpnn, 203: self.cb, 211: self.outna, 219: self.inan, 227: self.exsphl,
            235: self.exdehl, 243: self.di, 251: self.ei,
            196: self.callnznn, 204: self.callznn, 212: self.callncnn, 220: self.callcnn, 228: self.callponn, 236: self.callpenn, 244: self.callpnn, 252: self.callmnn,
            197: self.pushbc, 213: self.pushde, 229: self.pushhl, 245: self.pushaf,
            198: self.addan, 206: self.adcan, 214: self.suban, 222: self.sbcan, 230: self.andan, 238: self.xoran, 246: self.oran, 254: self.cpan,
            199: self.rst0, 207: self.rst8, 215: self.rst16, 223: self.rst24, 231: self.rst32, 239: self.rst40, 247: self.rst48, 255: self.rst56,
            205: self.callnn, 221: self.ix, 237: self.ed, 253: self.iy, 
        }

        self._ixiydict = {
            9: self.addidbc, 25: self.addidde, 41: self.addidid, 57: self.addidsp,
            33: self.ldidnn, 34: self.ldtonnid, 42: self.ldidfromnn,
            35: self.incid, 36: self.incidh, 44: self.incidl, 52: self.incinidd,
            43: self.decid, 37: self.decidh, 45: self.decidl, 53: self.decinidd,
            68: self.ldbidh, 76: self.ldcidh, 84: self.lddidh, 92: self.ldeidh, 124: self.ldaidh,
            69: self.ldbidl, 77: self.ldcidl, 85: self.lddidl, 93: self.ldeidl, 125: self.ldaidl,
            96: self.ldidhb, 97: self.ldidhc, 98: self.ldidhd, 99: self.ldidhe, 100: self.ldidhidh, 101: self.ldidhidl, 38: self.ldidhn, 103: self.ldidha,
            104: self.ldidlb, 105: self.ldidlc, 106: self.ldidld, 107: self.ldidle, 108: self.ldidlidh, 109: self.ldidlidl, 46: self.ldidln, 111: self.ldidla,
            70: self.ldbfromidd, 78: self.ldcfromidd, 86: self.lddfromidd, 94: self.ldefromidd, 102: self.ldhfromidd, 110: self.ldlfromidd, 126: self.ldafromidd,
            112: self.ldtoiddb, 113: self.ldtoiddc, 114: self.ldtoiddd, 115: self.ldtoidde, 116: self.ldtoiddh, 117: self.ldtoiddl, 54: self.ldtoiddn, 119: self.ldtoidda,
            132: self.addaidh, 133: self.addaidl, 134: self.addafromidd, 140: self.adcaidh, 141: self.adcaidl, 142: self.adcafromidd,
            148: self.subaidh, 149: self.subaidl, 150: self.subafromidd, 156: self.sbcaidh, 157: self.sbcaidl, 158: self.sbcafromidd,
            164: self.andaidh, 165: self.andaidl, 166: self.andafromidd, 172: self.xoraidh, 173: self.xoraidl, 174: self.xorafromidd, 180: self.oraidh, 181: self.oraidl, 182: self.orafromidd,
            188: self.cpaidh, 189: self.cpaidl, 190: self.cpafromidd,
            229: self.pushid, 225: self.popid, 233: self.jpid, 249: self.ldspid, 227: self.exfromspid,
            203: self.idcb
        }

        self._idcbdict = {
            0: self.cbrlcb, 1: self.cbrlcc, 2: self.cbrlcd, 3: self.cbrlce, 4: self.cbrlch, 5: self.cbrlcl, 6: self.cbrlcinhl, 7: self.cbrlca,
            8: self.cbrrcb, 9: self.cbrrcc, 10: self.cbrrcd, 11: self.cbrrce, 12: self.cbrrch, 13: self.cbrrcl, 14: self.cbrrcinhl, 15: self.cbrrca,
            16: self.cbrlb, 17: self.cbrlc, 18: self.cbrld, 19: self.cbrle, 20: self.cbrlh, 21: self.cbrll, 22: self.cbrlinhl, 23: self.cbrla,
            24: self.cbrrb, 25: self.cbrrc, 26: self.cbrrd, 27: self.cbrre, 28: self.cbrrh, 29: self.cbrrl, 30: self.cbrrinhl, 31: self.cbrra,
            32: self.cbslab, 33: self.cbslac, 34: self.cbslad, 35: self.cbslae, 36: self.cbslah, 37: self.cbslal, 38: self.cbslainhl, 39: self.cbslaa,
            40: self.cbsrab, 41: self.cbsrac, 42: self.cbsrad, 43: self.cbsrae, 44: self.cbsrah, 45: self.cbsral, 46: self.cbsrainhl, 47: self.cbsraa,
            48: self.cbslsb, 49: self.cbslsc, 50: self.cbslsd, 51: self.cbslse, 52: self.cbslsh, 53: self.cbslsl, 54: self.cbslsinhl, 55: self.cbslsa,
            56: self.cbsrlb, 57: self.cbsrlc, 58: self.cbsrld, 59: self.cbsrle, 60: self.cbsrlh, 61: self.cbsrll, 62: self.cbsrlinhl, 63: self.cbsrla,
            64: self.cbbit0, 65: self.cbbit0, 66: self.cbbit0, 67: self.cbbit0, 68: self.cbbit0, 69: self.cbbit0, 70: self.cbbit0, 71: self.cbbit0,
            72: self.cbbit1, 73: self.cbbit1, 74: self.cbbit1, 75: self.cbbit1, 76: self.cbbit1, 77: self.cbbit1, 78: self.cbbit1, 79: self.cbbit1,
            80: self.cbbit2, 81: self.cbbit2, 82: self.cbbit2, 83: self.cbbit2, 84: self.cbbit2, 85: self.cbbit2, 86: self.cbbit2, 87: self.cbbit2,
            88: self.cbbit3, 89: self.cbbit3, 90: self.cbbit3, 91: self.cbbit3, 92: self.cbbit3, 93: self.cbbit3, 94: self.cbbit3, 95: self.cbbit3,
            96: self.cbbit4, 97: self.cbbit4, 98: self.cbbit4, 99: self.cbbit4, 100: self.cbbit4, 101: self.cbbit4, 102: self.cbbit4, 103: self.cbbit4,
            104: self.cbbit5, 105: self.cbbit5, 106: self.cbbit5, 107: self.cbbit5, 108: self.cbbit5, 109: self.cbbit5, 110: self.cbbit5, 111: self.cbbit5,
            112: self.cbbit6, 113: self.cbbit6, 114: self.cbbit6, 115: self.cbbit6, 116: self.cbbit6, 117: self.cbbit6, 118: self.cbbit6, 119: self.cbbit6,
            120: self.cbbit7, 121: self.cbbit7, 122: self.cbbit7, 123: self.cbbit7, 124: self.cbbit7, 125: self.cbbit7, 126: self.cbbit7, 127: self.cbbit7,
            128: self.cbres0b, 129: self.cbres0c, 130: self.cbres0d, 131: self.cbres0e, 132: self.cbres0h, 133: self.cbres0l, 134: self.cbres0inhl, 135: self.cbres0a,
            136: self.cbres1b, 137: self.cbres1c, 138: self.cbres1d, 139: self.cbres1e, 140: self.cbres1h, 141: self.cbres1l, 142: self.cbres1inhl, 143: self.cbres1a,
            144: self.cbres2b, 145: self.cbres2c, 146: self.cbres2d, 147: self.cbres2e, 148: self.cbres2h, 149: self.cbres2l, 150: self.cbres2inhl, 151: self.cbres2a,
            152: self.cbres3b, 153: self.cbres3c, 154: self.cbres3d, 155: self.cbres3e, 156: self.cbres3h, 157: self.cbres3l, 158: self.cbres3inhl, 159: self.cbres3a,
            160: self.cbres4b, 161: self.cbres4c, 162: self.cbres4d, 163: self.cbres4e, 164: self.cbres4h, 165: self.cbres4l, 166: self.cbres4inhl, 167: self.cbres4a,
            168: self.cbres5b, 169: self.cbres5c, 170: self.cbres5d, 171: self.cbres5e, 172: self.cbres5h, 173: self.cbres5l, 174: self.cbres5inhl, 175: self.cbres5a,
            176: self.cbres6b, 177: self.cbres6c, 178: self.cbres6d, 179: self.cbres6e, 180: self.cbres6h, 181: self.cbres6l, 182: self.cbres6inhl, 183: self.cbres6a,
            184: self.cbres7b, 185: self.cbres7c, 186: self.cbres7d, 187: self.cbres7e, 188: self.cbres7h, 189: self.cbres7l, 190: self.cbres7inhl, 191: self.cbres7a,
            192: self.cbset0b, 193: self.cbset0c, 194: self.cbset0d, 195: self.cbset0e, 196: self.cbset0h, 197: self.cbset0l, 198: self.cbset0inhl, 199: self.cbset0a,
            200: self.cbset1b, 201: self.cbset1c, 202: self.cbset1d, 203: self.cbset1e, 204: self.cbset1h, 205: self.cbset1l, 206: self.cbset1inhl, 207: self.cbset1a,
            208: self.cbset2b, 209: self.cbset2c, 210: self.cbset2d, 211: self.cbset2e, 212: self.cbset2h, 213: self.cbset2l, 214: self.cbset2inhl, 215: self.cbset2a,
            216: self.cbset3b, 217: self.cbset3c, 218: self.cbset3d, 219: self.cbset3e, 220: self.cbset3h, 221: self.cbset3l, 222: self.cbset3inhl, 223: self.cbset3a,
            224: self.cbset4b, 225: self.cbset4c, 226: self.cbset4d, 227: self.cbset4e, 228: self.cbset4h, 229: self.cbset4l, 230: self.cbset4inhl, 231: self.cbset4a,
            232: self.cbset5b, 233: self.cbset5c, 234: self.cbset5d, 235: self.cbset5e, 236: self.cbset5h, 237: self.cbset5l, 238: self.cbset5inhl, 239: self.cbset5a,
            240: self.cbset6b, 241: self.cbset6c, 242: self.cbset6d, 243: self.cbset6e, 244: self.cbset6h, 245: self.cbset6l, 246: self.cbset6inhl, 247: self.cbset6a,
            248: self.cbset7b, 249: self.cbset7c, 250: self.cbset7d, 251: self.cbset7e, 252: self.cbset7h, 253: self.cbset7l, 254: self.cbset7inhl, 255: self.cbset7a
        }
    
    def setflags(self):
        self._fS = (self._F[0] & F_S) != 0
        self._fZ = (self._F[0] & F_Z) != 0
        self._f5 = (self._F[0] & F_5) != 0
        self._fH = (self._F[0] & F_H) != 0
        self._f3 = (self._F[0] & F_3) != 0
        self._fPV = (self._F[0] & F_PV) != 0
        self._fN = (self._F[0] & F_N) != 0
        self._fC = (self._F[0] & F_C) != 0

    def inc_r(self, r=1):
        self._R_b[0] = ((self._R_b[0] + r) % 128) + self._R7_b
    
    # Stack access
    def pushw(self, word):
        self._SP[0] = (self._SP[0] - 2) % 65536
        self.memory.pokew(self._SP[0], word)
    
    def popw(self):
        t = self.memory.peekw(self._SP[0])
        self._SP[0] = (self._SP[0] + 2) % 65536
        return t
    
    # Call stack
    def pushpc(self):
        self.pushw(self._PC[0])
    
    def poppc(self):
        self._PC[0] = self.popw()
    
    def nxtpcb(self):
        t = self.memory.peekb(self._PC[0])
        self._PC[0] = (self._PC[0] + 1) % 65536
        return t
    
    def nxtpcsb(self):
        t = self.memory.peeksb(self._PC[0])
        self._PC[0] = (self._PC[0] + 1) % 65536
        if self.show_debug_info:
            print(f'signedbyte: {t}, PC: 0x{self._PC[0]:4x}')
        return t
    
    def incpcsb(self):
        t = self.nxtpcsb()
        self._PC[0] = (self._PC[0] + t) % 65536
    
    def nxtpcw(self):
        t = self.memory.peekw(self._PC[0])
        self._PC[0] = (self._PC[0] + 2) % 65536
        return t
    
    # Reset all registers to power on state
    def reset(self):
        self._PC[0] = 0
        self._SP[0] = 0
    
        self._fS = False
        self._fZ = False
        _f5 = False
        self._fH = False
        self._f3 = False
        self._fPV = False
        self._fN = False
        self._fC = False
        self._AF[0] = 0
        self._BC[0] = 0
        self._DE[0] = 0
        self._HL[0] = 0
    
        self._AF_[0] = 0
        self._BC_[0] = 0
        self._DE_[0] = 0
        self._HL_[0] = 0
    
        self._IX[0] = 0
        self._IY[0] = 0
        self._R = 0
        # _Ifull[0] = 0
        self._IFF1 = 0
        self._IFF2 = 0
        self._IM = IM0

        self.video_update_time = 0

    def show_registers(self):
        print(f'PC: 0x{self._PC[0]:04x}\tOPCODE: {self.memory.peekb(self._PC[0]):03d}\tA: 0x{self._A[0]:02x}\tHL: 0x{self._HL[0]:04x}\tBC: 0x{self._BC[0]:04x}\tDE: 0x{self._DE[0]:04x}')
        print(f'FLAGS 0x{self._F[0]:02x}\tC: {self._fC}\tN: {self._fN}\tPV: {self._fPV}\t3: {self._f3}\tH: {self._fH}\t5: {self._f5}\tZ: {self._fZ}\tS: {self._fS}')
        print(f'IFF1 {self._IFF1}, IFF2 {self._IFF2}')

    def interruptCPU(self):
        # If not a non-maskable interrupt
        def im0im1():
            self.pushpc()
            self._IFF1 = False
            self._IFF2 = False
            self._PC[0] = 56
            return 13
    
        def im2():
            self.pushpc()
            self._IFF1 = False
            self._IFF2 = False
            # self._PC[0] = self.memory.peekw(_Ifull[0])
            self._PC[0] = self.memory.peekw(self._I[0]*256+255)
            return 19
    
        if not self._IFF1:
            # if self.show_debug_info:
            #    print('NO interrupt')
            return 0
        if self.show_debug_info:
            print(f'Interrupt: {self._IM}, PC: 0x{self._PC[0]:4x}, IFF1: {self._IFF1}')
        return {IM0: im0im1, IM1: im0im1, IM2: im2}.get(self._IM)()

    def execute(self):
    
        while True:
            self.clock_cycle_test(self)
            self.inc_r()
            if self.show_debug_info:
                self.show_registers()
            opcode = self.nxtpcb()
            if opcode == 118:  # HALT
                halts_to_interrupt = int(((-self.local_clock_cycles_counter - 1) / 4) + 1)
                self.local_clock_cycles_counter += (halts_to_interrupt * 4)
                self.inc_r(halts_to_interrupt - 1)
                continue
            else:
                self.local_clock_cycles_counter += self.main_cmds.get(opcode)()
    
    def execute_id(self):
        self.inc_r()
        opcode = self.nxtpcb()
        return self._ixiydict.get(opcode, self.nop)()
    
    def execute_id_cb(self, opcode, z):
        return self._idcbdict.get(opcode)(z)
    
    @staticmethod
    def nop():
        return 4
    
    # EXX
    def exx(self):
        self._HL, self._HL_ = self._HL_, self._HL
        self._H, self._H_ = self._H_, self._H
        self._L, self._L_ = self._L_, self._L
    
        self._DE, self._DE_ = self._DE_, self._DE
        self._D, self._D_ = self._D_, self._D
        self._E, self._E_ = self._E_, self._E
    
        self._BC, self._BC_ = self._BC_, self._BC
        self._B, self._B_ = self._B_, self._B
        self._C, self._C_ = self._C_, self._C
        return 4
    
    # EX AF,AF'
    def ex_af_af(self):
        self._F[0] = (F_S if self._fS else 0) + \
            (F_Z if self._fZ else 0) + \
            (F_5 if self._f5 else 0) + \
            (F_H if self._fH else 0) + \
            (F_3 if self._f3 else 0) + \
            (F_PV if self._fPV else 0) + \
            (F_N if self._fN else 0) + \
            (F_C if self._fC else 0)
        self._AF, self._AF_ = self._AF_, self._AF
        self._A, self._A_ = self._A_, self._A
        self._F, self._F_ = self._F_, self._F
        self.setflags()
        return 4
    
    def djnz(self):
        self._B[0] = self.qdec8(self._B[0])
        if self._B[0] != 0:
            self.incpcsb()
            return 13
        else:
            self._PC[0] = self.inc16(self._PC[0])
            return 8
    
    def jr(self):
        self.incpcsb()
        return 12
    
    def jrnz(self):
        if not self._fZ:
            self.incpcsb()
            return 12
        else:
            self._PC[0] = self.inc16(self._PC[0])
            return 7
    
    def jrz(self):
        if self._fZ:
            self.incpcsb()
            return 12
        else:
            self._PC[0] = self.inc16(self._PC[0])
            return 7
    
    def jrnc(self):
        if not self._fC:
            self.incpcsb()
            return 12
        else:
            self._PC[0] = self.inc16(self._PC[0])
            return 7
    
    def jrc(self):
        if self._fC:
            self.incpcsb()
            return 12
        else:
            self._PC[0] = self.inc16(self._PC[0])
            return 7
    
    # LD self.rr,nn / ADD HL,self.rr
    def ldbcnn(self):
        self._BC[0] = self.nxtpcw()
        return 10
    
    def addhlbc(self):
        self._HL[0] = self.add16(self._HL[0], self._BC[0])
        return 11
    
    def lddenn(self):
        self._DE[0] = self.nxtpcw()
        return 10
    
    def addhlde(self):
        self._HL[0] = self.add16(self._HL[0], self._DE[0])
        return 11
    
    def ldhlnn(self):
        self._HL[0] = self.nxtpcw()
        return 10
    
    def addhlhl(self):
        hl = self._HL[0]
        self._HL[0] = self.add16(hl, hl)
        return 11
    
    def ldspnn(self):
        self._SP[0] = self.nxtpcw()
        return 10
    
    def addhlsp(self):
        self._HL[0] = self.add16(self._HL[0], self._SP[0])
        return 11
    
    # LD (**),A/A,(**)
    def ldtobca(self):
        self.memory.pokeb(self._BC[0], self._A[0])
        return 7
    
    def ldafrombc(self):
        self._A[0] = self.memory.peekb(self._BC[0])
        return 7
    
    def ldtodea(self):
        self.memory.pokeb(self._DE[0], self._A[0])
        return 7
    
    def ldafromde(self):
        self._A[0] = self.memory.peekb(self._DE[0])
        return 7
    
    def ldtonnhl(self):
        self.memory.pokew(self.nxtpcw(), self._HL[0])
        return 16
    
    def ldhlfromnn(self):
        self._HL[0] = self.memory.peekw(self.nxtpcw())
        return 16
    
    def ldtonna(self):
        self.memory.pokeb(self.nxtpcw(), self._A[0])
        return 13
    
    def ldafromnn(self):
        self._A[0] = self.memory.peekb(self.nxtpcw())
        return 13
    
    # INC/DEC *
    def incbc(self):
        self._BC[0] = self.inc16(self._BC[0])
        return 6
    
    def decbc(self):
        self._BC[0] = self.dec16(self._BC[0])
        return 6
    
    def incde(self):
        self._DE[0] = self.inc16(self._DE[0])
        return 6
    
    def decde(self):
        self._DE[0] = self.dec16(self._DE[0])
        return 6
    
    def inchl(self):
        self._HL[0] = self.inc16(self._HL[0])
        return 6
    
    def dechl(self):
        self._HL[0] = self.dec16(self._HL[0])
        return 6
    
    def incsp(self):
        self._SP[0] = self.inc16(self._SP[0])
        return 6
    
    def decsp(self):
        self._SP[0] = self.dec16(self._SP[0])
        return 6
    
    # INC *
    def incb(self):
        self._B[0] = self.inc8(self._B[0])
        return 4
    
    def incc(self):
        self._C[0] = self.inc8(self._C[0])
        return 4
    
    def incd(self):
        self._D[0] = self.inc8(self._D[0])
        return 4
    
    def ince(self):
        self._E[0] = self.inc8(self._E[0])
        return 4
    
    def inch(self):
        self._H[0] = self.inc8(self._H[0])
        return 4
    
    def incl(self):
        self._L[0] = self.inc8(self._L[0])
        return 4
    
    def incinhl(self):
        self.memory.pokeb(self._HL[0], self.inc8(self.memory.peekb(self._HL[0])))
        return 11
    
    def inca(self):
        self._A[0] = self.inc8(self._A[0])
        return 4
    
    # DEC *
    def decb(self):
        self._B[0] = self.dec8(self._B[0])
        return 4
    
    def decc(self):
        self._C[0] = self.dec8(self._C[0])
        return 4
    
    def decd(self):
        self._D[0] = self.dec8(self._D[0])
        return 4
    
    def dece(self):
        self._E[0] = self.dec8(self._E[0])
        return 4
    
    def dech(self):
        self._H[0] = self.dec8(self._H[0])
        return 4
    
    def decl(self):
        self._L[0] = self.dec8(self._L[0])
        return 4
    
    def decinhl(self):
        self.memory.pokeb(self._HL[0], self.dec8(self.memory.peekb(self._HL[0])))
        return 11
    
    def deca(self):
        self._A[0] = self.dec8(self._A[0])
        return 4
    
    # LD *,N
    def ldbn(self):
        self._B[0] = self.nxtpcb()
        return 7
    
    def ldcn(self):
        self._C[0] = self.nxtpcb()
        return 7
    
    def lddn(self):
        self._D[0] = self.nxtpcb()
        return 7
    
    def lden(self):
        self._E[0] = self.nxtpcb()
        return 7
    
    def ldhn(self):
        self._H[0] = self.nxtpcb()
        return 7
    
    def ldln(self):
        self._L[0] = self.nxtpcb()
        return 7
    
    def ldtohln(self):
        self.memory.pokeb(self._HL[0], self.nxtpcb())
        return 10
    
    def ldan(self):
        self._A[0] = self.nxtpcb()
        return 7
    
    # R**A
    def rlca(self):
        ans = self._A[0]
        c = ans > 0x7f
        ans = ((ans << 1) + (0x01 if c else 0)) % 256
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fN = False
        self._fH = False
        self._fC = c
        self._A[0] = ans
        return 4
    
    # Rotate Left through Carry - alters H N C 3 5 flags (CHECKED)
    def rla(self):
        ans = self._A[0]
        c = ans > 0x7F
        ans = ((ans << 1) + (1 if self._fC else 0)) % 256
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fN = False
        self._fH = False
        self._fC = c
        self._A[0] = ans
        return 4
    
    # Rotate Right - alters H N C 3 5 flags (CHECKED)
    def rrca(self):
        ans = self._A[0]
        c = (ans % 2) != 0
        ans = ((ans >> 1) + (0x80 if c else 0)) % 256
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fN = False
        self._fH = False
        self._fC = c
        self._A[0] = ans
        return 4
    
    # Rotate Right through Carry - alters H N C 3 5 flags (CHECKED)
    def rra(self):
        ans = self._A[0]
        c = (ans % 2) != 0
        ans = ((ans >> 1) + (0x80 if self._fC else 0)) % 256
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fN = False
        self._fH = False
        self._fC = c
        self._A[0] = ans
        return 4
    
    # Decimal Adjust Accumulator - alters all flags (CHECKED)
    def daa(self):
        ans = self._A[0]
        incr = 0
        carry = self._fC
    
        if self._fH or ((ans % 16) > 0x09):
            incr |= 0x06
    
        if carry or (ans > 0x9f) or ((ans > 0x8f) and ((ans % 16) > 0x09)):
            incr |= 0x60
    
        if ans > 0x99:
            carry = True
    
        if self._fN:
            self.sub_a(incr)
        else:
            self.add_a(incr)
    
        ans = self._A[0]
        self._fC = carry
        self._fPV = self.parity[ans]
        return 4
    
    # One's complement - alters N H 3 5 flags (CHECKED)
    def cpla(self):
        ans = self._A[0] ^ 0xff
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fH = True
        self._fN = True
        self._A[0] = ans
        return 4
    
    # self.set carry flag - alters N H 3 5 C flags (CHECKED)
    def scf(self):
        ans = self._A[0]
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fN = False
        self._fH = False
        self._fC = True
        return 4
    
    # Complement carry flag - alters N 3 5 C flags (CHECKED)
    def ccf(self):
        ans = self._A[0]
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fH = self._fC
        self._fC = not self._fC
        self._fN = False
        return 4
    
    # LD B,*
    @staticmethod
    def ldbb():
        return 4
    
    def ldbc(self):
        self._B[0] = self._C[0]
        return 4
    
    def ldbd(self):
        self._B[0] = self._D[0]
        return 4
    
    def ldbe(self):
        self._B[0] = self._E[0]
        return 4
    
    def ldbh(self):
        self._B[0] = self._H[0]
        return 4
    
    def ldbl(self):
        self._B[0] = self._L[0]
        return 4
    
    def ldbfromhl(self):
        self._B[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldba(self):
        self._B[0] = self._A[0]
        return 4
    
    # LD C,*
    def ldcb(self):
        self._C[0] = self._B[0]
        return 4
    
    @staticmethod
    def ldcc():
        return 4
    
    def ldcd(self):
        self._C[0] = self._D[0]
        return 4
    
    def ldce(self):
        self._C[0] = self._E[0]
        return 4
    
    def ldch(self):
        self._C[0] = self._H[0]
        return 4
    
    def ldcl(self):
        self._C[0] = self._L[0]
        return 4
    
    def ldcfromhl(self):
        self._C[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldca(self):
        self._C[0] = self._A[0]
        return 4
    
    # LD D,*
    def lddb(self):
        self._D[0] = self._B[0]
        return 4
    
    def lddc(self):
        self._D[0] = self._C[0]
        return 4
    
    @staticmethod
    def lddd():
        return 4
    
    def ldde(self):
        self._D[0] = self._E[0]
        return 4
    
    def lddh(self):
        self._D[0] = self._H[0]
        return 4
    
    def lddl(self):
        self._D[0] = self._L[0]
        return 4
    
    def lddfromhl(self):
        self._D[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldda(self):
        self._D[0] = self._A[0]
        return 4
    
    # LD E,*
    def ldeb(self):
        self._E[0] = self._B[0]
        return 4
    
    def ldec(self):
        self._E[0] = self._C[0]
        return 4
    
    def lded(self):
        self._E[0] = self._D[0]
        return 4
    
    @staticmethod
    def ldee():
        return 4
    
    def ldeh(self):
        self._E[0] = self._H[0]
        return 4
    
    def ldel(self):
        self._E[0] = self._L[0]
        return 4
    
    def ldefromhl(self):
        self._E[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldea(self):
        self._E[0] = self._A[0]
        return 4
    
    # LD H,*
    def ldhb(self):
        self._H[0] = self._B[0]
        return 4
    
    def ldhc(self):
        self._H[0] = self._C[0]
        return 4
    
    def ldhd(self):
        self._H[0] = self._D[0]
        return 4
    
    def ldhe(self):
        self._H[0] = self._E[0]
        return 4
    
    @staticmethod
    def ldhh():
        return 4
    
    def ldhl(self):
        self._H[0] = self._L[0]
        return 4
    
    def ldhfromhl(self):
        self._H[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldha(self):
        self._H[0] = self._A[0]
        return 4
    
    # LD L,*
    def ldlb(self):
        self._L[0] = self._B[0]
        return 4
    
    def ldlc(self):
        self._L[0] = self._C[0]
        return 4
    
    def ldld(self):
        self._L[0] = self._D[0]
        return 4
    
    def ldle(self):
        self._L[0] = self._E[0]
        return 4
    
    def ldlh(self):
        self._L[0] = self._H[0]
        return 4
    
    @staticmethod
    def ldll():
        return 4
    
    def ldlfromhl(self):
        self._L[0] = self.memory.peekb(self._HL[0])
        return 7
    
    def ldla(self):
        self._L[0] = self._A[0]
        return 4
    
    # LD (HL),*
    def ldtohlb(self):
        self.memory.pokeb(self._HL[0], self._B[0])
        return 7
    
    def ldtohlc(self):
        self.memory.pokeb(self._HL[0], self._C[0])
        return 7
    
    def ldtohld(self):
        self.memory.pokeb(self._HL[0], self._D[0])
        return 7
    
    def ldtohle(self):
        self.memory.pokeb(self._HL[0], self._E[0])
        return 7
    
    def ldtohlh(self):
        self.memory.pokeb(self._HL[0], self._H[0])
        return 7
    
    def ldtohll(self):
        self.memory.pokeb(self._HL[0], self._L[0])
        return 7
    
    def ldtohla(self):
        self.memory.pokeb(self._HL[0], self._A[0])
        return 7
    
    # LD A,*
    def ldab(self):
        self._A[0] = self._B[0]
        return 4
    
    def ldac(self):
        self._A[0] = self._C[0]
        return 4
    
    def ldad(self):
        self._A[0] = self._D[0]
        return 4
    
    def ldae(self):
        self._A[0] = self._E[0]
        return 4
    
    def ldah(self):
        self._A[0] = self._H[0]
        return 4
    
    def ldal(self):
        self._A[0] = self._L[0]
        return 4
    
    def ldafromhl(self):
        self._A[0] = self.memory.peekb(self._HL[0])
        return 7
    
    @staticmethod
    def ldaa():
        return 4
    
    # ADD A,*
    def addab(self):
        self.add_a(self._B[0])
        return 4
    
    def addac(self):
        self.add_a(self._C[0])
        return 4
    
    def addad(self):
        self.add_a(self._D[0])
        return 4
    
    def addae(self):
        self.add_a(self._E[0])
        return 4
    
    def addah(self):
        self.add_a(self._H[0])
        return 4
    
    def addal(self):
        self.add_a(self._L[0])
        return 4
    
    def addafromhl(self):
        self.add_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def addaa(self):
        self.add_a(self._A[0])
        return 4
    
    # ADC A,*
    def adcab(self):
        self.adc_a(self._B[0])
        return 4
    
    def adcac(self):
        self.adc_a(self._C[0])
        return 4
    
    def adcad(self):
        self.adc_a(self._D[0])
        return 4
    
    def adcae(self):
        self.adc_a(self._E[0])
        return 4
    
    def adcah(self):
        self.adc_a(self._H[0])
        return 4
    
    def adcal(self):
        self.adc_a(self._L[0])
        return 4
    
    def adcafromhl(self):
        self.adc_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def adcaa(self):
        self.adc_a(self._A[0])
        return 4
    
    # SUB A,*
    def subab(self):
        self.sub_a(self._B[0])
        return 4
    
    def subac(self):
        self.sub_a(self._C[0])
        return 4
    
    def subad(self):
        self.sub_a(self._D[0])
        return 4
    
    def subae(self):
        self.sub_a(self._E[0])
        return 4
    
    def subah(self):
        self.sub_a(self._H[0])
        return 4
    
    def subal(self):
        self.sub_a(self._L[0])
        return 4
    
    def subafromhl(self):
        self.sub_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def subaa(self):
        self.sub_a(self._A[0])
        return 4
    
    # SBC A,*
    def sbcab(self):
        self.sbc_a(self._B[0])
        return 4
    
    def sbcac(self):
        self.sbc_a(self._C[0])
        return 4
    
    def sbcad(self):
        self.sbc_a(self._D[0])
        return 4
    
    def sbcae(self):
        self.sbc_a(self._E[0])
        return 4
    
    def sbcah(self):
        self.sbc_a(self._H[0])
        return 4
    
    def sbcal(self):
        self.sbc_a(self._L[0])
        return 4
    
    def sbcafromhl(self):
        self.sbc_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def sbcaa(self):
        self.sbc_a(self._A[0])
        return 4
    
    # AND A,*
    def andab(self):
        self.and_a(self._B[0])
        return 4
    
    def andac(self):
        self.and_a(self._C[0])
        return 4
    
    def andad(self):
        self.and_a(self._D[0])
        return 4
    
    def andae(self):
        self.and_a(self._E[0])
        return 4
    
    def andah(self):
        self.and_a(self._H[0])
        return 4
    
    def andal(self):
        self.and_a(self._L[0])
        return 4
    
    def andafromhl(self):
        self.and_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def andaa(self):
        self.and_a(self._A[0])
        return 4
    
    # XOR A,*
    def xorab(self):
        self.xor_a(self._B[0])
        return 4
    
    def xorac(self):
        self.xor_a(self._C[0])
        return 4
    
    def xorad(self):
        self.xor_a(self._D[0])
        return 4
    
    def xorae(self):
        self.xor_a(self._E[0])
        return 4
    
    def xorah(self):
        self.xor_a(self._H[0])
        return 4
    
    def xoral(self):
        self.xor_a(self._L[0])
        return 4
    
    def xorafromhl(self):
        self.xor_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def xoraa(self):
        self.xor_a(self._A[0])
        return 4
    
    # OR A,*
    def orab(self):
        self.or_a(self._B[0])
        return 4
    
    def orac(self):
        self.or_a(self._C[0])
        return 4
    
    def orad(self):
        self.or_a(self._D[0])
        return 4
    
    def orae(self):
        self.or_a(self._E[0])
        return 4
    
    def orah(self):
        self.or_a(self._H[0])
        return 4
    
    def oral(self):
        self.or_a(self._L[0])
        return 4
    
    def orafromhl(self):
        self.or_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def oraa(self):
        self.or_a(self._A[0])
        return 4
    
    # CP A,*
    def cpab(self):
        self.cp_a(self._B[0])
        return 4
    
    def cpac(self):
        self.cp_a(self._C[0])
        return 4
    
    def cpad(self):
        self.cp_a(self._D[0])
        return 4
    
    def cpae(self):
        self.cp_a(self._E[0])
        return 4
    
    def cpah(self):
        self.cp_a(self._H[0])
        return 4
    
    def cpal(self):
        self.cp_a(self._L[0])
        return 4
    
    def cpafromhl(self):
        self.cp_a(self.memory.peekb(self._HL[0]))
        return 7
    
    def cpaa(self):
        self.cp_a(self._A[0])
        return 4
    
    # RET cc
    def retnz(self):
        if not self._fZ:
            self.poppc()
            return 11
        else:
            return 5
    
    def retz(self):
        if self._fZ:
            self.poppc()
            return 11
        else:
            return 5
    
    def retnc(self):
        if not self._fC:
            self.poppc()
            return 11
        else:
            return 5
    
    def retc(self):
        if self._fC:
            self.poppc()
            return 11
        else:
            return 5
    
    def retpo(self):
        if not self._fPV:
            self.poppc()
            return 11
        else:
            return 5
    
    def retpe(self):
        if self._fPV:
            self.poppc()
            return 11
        else:
            return 5
    
    def retp(self):
        if not self._fS:
            self.poppc()
            return 11
        else:
            return 5
    
    def retm(self):
        if self._fS:
            self.poppc()
            return 11
        else:
            return 5
    
    # POP
    def popbc(self):
        self._BC[0] = self.popw()
        return 10
    
    def popde(self):
        self._DE[0] = self.popw()
        return 10
    
    def pophl(self):
        self._HL[0] = self.popw()
        return 10
    
    def popaf(self):
        self._AF[0] = self.popw()
        self.setflags()
        return 10
    
    # JP cc,nn
    def jpnznn(self):
        if not self._fZ:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jpznn(self):
        if self._fZ:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jpncnn(self):
        if not self._fC:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jpcnn(self):
        if self._fC:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jpponn(self):
        if not self._fPV:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jppenn(self):
        if self._fPV:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jppnn(self):
        if not self._fS:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    def jpmnn(self):
        if self._fS:
            self._PC[0] = self.nxtpcw()
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
        return 10
    
    # Various
    def jphl(self):
        self._PC[0] = self._HL[0]
        return 4
    
    def ldsphl(self):
        self._SP[0] = self._HL[0]
        return 6
    
    def ret(self):
        self.poppc()
        return 10
    
    def jpnn(self):
        self._PC[0] = self.nxtpcw()
        return 10
    
    # CB prefix
    # self.rlc *
    def rlcb(self):
        self._B[0] = self.rlc(self._B[0])
        return 8
    
    def rlcc(self):
        self._C[0] = self.rlc(self._C[0])
        return 8
    
    def rlcd(self):
        self._D[0] = self.rlc(self._D[0])
        return 8
    
    def rlce(self):
        self._E[0] = self.rlc(self._E[0])
        return 8
    
    def rlch(self):
        self._H[0] = self.rlc(self._H[0])
        return 8
    
    def rlcl(self):
        self._L[0] = self.rlc(self._L[0])
        return 8
    
    def rlcfromhl(self):
        self.memory.pokeb(self._HL[0], self.rlc(self.memory.peekb(self._HL[0])))
        return 15
    
    def rlc_a(self):
        self._A[0] = self.rlc(self._A[0])
        return 8
    
    # self.rrc *
    def rrcb(self):
        self._B[0] = self.rrc(self._B[0])
        return 8
    
    def rrcc(self):
        self._C[0] = self.rrc(self._C[0])
        return 8
    
    def rrcd(self):
        self._D[0] = self.rrc(self._D[0])
        return 8
    
    def rrce(self):
        self._E[0] = self.rrc(self._E[0])
        return 8
    
    def rrch(self):
        self._H[0] = self.rrc(self._H[0])
        return 8
    
    def rrcl(self):
        self._L[0] = self.rrc(self._L[0])
        return 8
    
    def rrcfromhl(self):
        self.memory.pokeb(self._HL[0], self.rrc(self.memory.peekb(self._HL[0])))
        return 15
    
    def rrc_a(self):
        self._A[0] = self.rrc(self._A[0])
        return 8
    
    # self.rl *
    def rlb(self):
        self._B[0] = self.rl(self._B[0])
        return 8
    
    def rl_c(self):
        self._C[0] = self.rl(self._C[0])
        return 8
    
    def rld(self):
        self._D[0] = self.rl(self._D[0])
        return 8
    
    def rle(self):
        self._E[0] = self.rl(self._E[0])
        return 8
    
    def rlh(self):
        self._H[0] = self.rl(self._H[0])
        return 8
    
    def rll(self):
        self._L[0] = self.rl(self._L[0])
        return 8
    
    def rlfromhl(self):
        self.memory.pokeb(self._HL[0], self.rl(self.memory.peekb(self._HL[0])))
        return 15
    
    def rl_a(self):
        self._A[0] = self.rl(self._A[0])
        return 8
    
    # self.rr *
    def rrb(self):
        self._B[0] = self.rr(self._B[0])
        return 8
    
    def rr_c(self):
        self._C[0] = self.rr(self._C[0])
        return 8
    
    def rrd(self):
        self._D[0] = self.rr(self._D[0])
        return 8
    
    def rre(self):
        self._E[0] = self.rr(self._E[0])
        return 8
    
    def rrh(self):
        self._H[0] = self.rr(self._H[0])
        return 8
    
    def rrl(self):
        self._L[0] = self.rr(self._L[0])
        return 8
    
    def rrfromhl(self):
        self.memory.pokeb(self._HL[0], self.rr(self.memory.peekb(self._HL[0])))
        return 15
    
    def rr_a(self):
        self._A[0] = self.rr(self._A[0])
        return 8
    
    # self.sla *
    def slab(self):
        self._B[0] = self.sla(self._B[0])
        return 8
    
    def slac(self):
        self._C[0] = self.sla(self._C[0])
        return 8
    
    def slad(self):
        self._D[0] = self.sla(self._D[0])
        return 8
    
    def slae(self):
        self._E[0] = self.sla(self._E[0])
        return 8
    
    def slah(self):
        self._H[0] = self.sla(self._H[0])
        return 8
    
    def slal(self):
        self._L[0] = self.sla(self._L[0])
        return 8
    
    def slafromhl(self):
        self.memory.pokeb(self._HL[0], self.sla(self.memory.peekb(self._HL[0])))
        return 15
    
    def sla_a(self):
        self._A[0] = self.sla(self._A[0])
        return 8
    
    # self.sra *
    def srab(self):
        self._B[0] = self.sra(self._B[0])
        return 8
    
    def srac(self):
        self._C[0] = self.sra(self._C[0])
        return 8
    
    def srad(self):
        self._D[0] = self.sra(self._D[0])
        return 8
    
    def srae(self):
        self._E[0] = self.sra(self._E[0])
        return 8
    
    def srah(self):
        self._H[0] = self.sra(self._H[0])
        return 8
    
    def sral(self):
        self._L[0] = self.sra(self._L[0])
        return 8
    
    def srafromhl(self):
        self.memory.pokeb(self._HL[0], self.sra(self.memory.peekb(self._HL[0])))
        return 15
    
    def sra_a(self):
        self._A[0] = self.sra(self._A[0])
        return 8
    
    # self.sls *
    def slsb(self):
        self._B[0] = self.sls(self._B[0])
        return 8
    
    def slsc(self):
        self._C[0] = self.sls(self._C[0])
        return 8
    
    def slsd(self):
        self._D[0] = self.sls(self._D[0])
        return 8
    
    def slse(self):
        self._E[0] = self.sls(self._E[0])
        return 8
    
    def slsh(self):
        self._H[0] = self.sls(self._H[0])
        return 8
    
    def slsl(self):
        self._L[0] = self.sls(self._L[0])
        return 8
    
    def slsfromhl(self):
        self.memory.pokeb(self._HL[0], self.sls(self.memory.peekb(self._HL[0])))
        return 15
    
    def sls_a(self):
        self._A[0] = self.sls(self._A[0])
        return 8
    
    # self.srl *
    def srlb(self):
        self._B[0] = self.srl(self._B[0])
        return 8
    
    def srlc(self):
        self._C[0] = self.srl(self._C[0])
        return 8
    
    def srld(self):
        self._D[0] = self.srl(self._D[0])
        return 8
    
    def srle(self):
        self._E[0] = self.srl(self._E[0])
        return 8
    
    def srlh(self):
        self._H[0] = self.srl(self._H[0])
        return 8
    
    def srll(self):
        self._L[0] = self.srl(self._L[0])
        return 8
    
    def srlfromhl(self):
        self.memory.pokeb(self._HL[0], self.srl(self.memory.peekb(self._HL[0])))
        return 15
    
    def srl_a(self):
        self._A[0] = self.srl(self._A[0])
        return 8
    
    # self.bit 0, *
    def bit0b(self):
        self.bit(0x01, self._B[0])
        return 8
    
    def bit0c(self):
        self.bit(0x01, self._C[0])
        return 8
    
    def bit0d(self):
        self.bit(0x01, self._D[0])
        return 8
    
    def bit0e(self):
        self.bit(0x01, self._E[0])
        return 8
    
    def bit0h(self):
        self.bit(0x01, self._H[0])
        return 8
    
    def bit0l(self):
        self.bit(0x01, self._L[0])
        return 8
    
    def bit0fromhl(self):
        self.bit(0x01, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit0a(self):
        self.bit(0x01, self._A[0])
        return 8
    
    # self.bit 1, *
    def bit1b(self):
        self.bit(0x02, self._B[0])
        return 8
    
    def bit1c(self):
        self.bit(0x02, self._C[0])
        return 8
    
    def bit1d(self):
        self.bit(0x02, self._D[0])
        return 8
    
    def bit1e(self):
        self.bit(0x02, self._E[0])
        return 8
    
    def bit1h(self):
        self.bit(0x02, self._H[0])
        return 8
    
    def bit1l(self):
        self.bit(0x02, self._L[0])
        return 8
    
    def bit1fromhl(self):
        self.bit(0x02, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit1a(self):
        self.bit(0x02, self._A[0])
        return 8
    
    # self.bit 2, *
    def bit2b(self):
        self.bit(0x04, self._B[0])
        return 8
    
    def bit2c(self):
        self.bit(0x04, self._C[0])
        return 8
    
    def bit2d(self):
        self.bit(0x04, self._D[0])
        return 8
    
    def bit2e(self):
        self.bit(0x04, self._E[0])
        return 8
    
    def bit2h(self):
        self.bit(0x04, self._H[0])
        return 8
    
    def bit2l(self):
        self.bit(0x04, self._L[0])
        return 8
    
    def bit2fromhl(self):
        self.bit(0x04, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit2a(self):
        self.bit(0x04, self._A[0])
        return 8
    
    # self.bit 3, *
    def bit3b(self):
        self.bit(0x08, self._B[0])
        return 8
    
    def bit3c(self):
        self.bit(0x08, self._C[0])
        return 8
    
    def bit3d(self):
        self.bit(0x08, self._D[0])
        return 8
    
    def bit3e(self):
        self.bit(0x08, self._E[0])
        return 8
    
    def bit3h(self):
        self.bit(0x08, self._H[0])
        return 8
    
    def bit3l(self):
        self.bit(0x08, self._L[0])
        return 8
    
    def bit3fromhl(self):
        self.bit(0x08, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit3a(self):
        self.bit(0x08, self._A[0])
        return 8
    
    # self.bit 4, *
    def bit4b(self):
        self.bit(0x10, self._B[0])
        return 8
    
    def bit4c(self):
        self.bit(0x10, self._C[0])
        return 8
    
    def bit4d(self):
        self.bit(0x10, self._D[0])
        return 8
    
    def bit4e(self):
        self.bit(0x10, self._E[0])
        return 8
    
    def bit4h(self):
        self.bit(0x10, self._H[0])
        return 8
    
    def bit4l(self):
        self.bit(0x10, self._L[0])
        return 8
    
    def bit4fromhl(self):
        self.bit(0x10, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit4a(self):
        self.bit(0x10, self._A[0])
        return 8
    
    # self.bit 5, *
    def bit5b(self):
        self.bit(0x20, self._B[0])
        return 8
    
    def bit5c(self):
        self.bit(0x20, self._C[0])
        return 8
    
    def bit5d(self):
        self.bit(0x20, self._D[0])
        return 8
    
    def bit5e(self):
        self.bit(0x20, self._E[0])
        return 8
    
    def bit5h(self):
        self.bit(0x20, self._H[0])
        return 8
    
    def bit5l(self):
        self.bit(0x20, self._L[0])
        return 8
    
    def bit5fromhl(self):
        self.bit(0x20, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit5a(self):
        self.bit(0x20, self._A[0])
        return 8
    
    # self.bit 6, *
    def bit6b(self):
        self.bit(0x40, self._B[0])
        return 8
    
    def bit6c(self):
        self.bit(0x40, self._C[0])
        return 8
    
    def bit6d(self):
        self.bit(0x40, self._D[0])
        return 8
    
    def bit6e(self):
        self.bit(0x40, self._E[0])
        return 8
    
    def bit6h(self):
        self.bit(0x40, self._H[0])
        return 8
    
    def bit6l(self):
        self.bit(0x40, self._L[0])
        return 8
    
    def bit6fromhl(self):
        self.bit(0x40, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit6a(self):
        self.bit(0x40, self._A[0])
        return 8
    
    # self.bit 7, *
    def bit7b(self):
        self.bit(0x80, self._B[0])
        return 8
    
    def bit7c(self):
        self.bit(0x80, self._C[0])
        return 8
    
    def bit7d(self):
        self.bit(0x80, self._D[0])
        return 8
    
    def bit7e(self):
        self.bit(0x80, self._E[0])
        return 8
    
    def bit7h(self):
        self.bit(0x80, self._H[0])
        return 8
    
    def bit7l(self):
        self.bit(0x80, self._L[0])
        return 8
    
    def bit7fromhl(self):
        self.bit(0x80, self.memory.peekb(self._HL[0]))
        return 12
    
    def bit7a(self):
        self.bit(0x80, self._A[0])
        return 8
    
    # self.res 0, *
    def res0b(self):
        self._B[0] = self.res(0x01, self._B[0])
        return 8
    
    def res0c(self):
        self._C[0] = self.res(0x01, self._C[0])
        return 8
    
    def res0d(self):
        self._D[0] = self.res(0x01, self._D[0])
        return 8
    
    def res0e(self):
        self._E[0] = self.res(0x01, self._E[0])
        return 8
    
    def res0h(self):
        self._H[0] = self.res(0x01, self._H[0])
        return 8
    
    def res0l(self):
        self._L[0] = self.res(0x01, self._L[0])
        return 8
    
    def res0fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x01, self.memory.peekb(self._HL[0])))
        return 15
    
    def res0a(self):
        self._A[0] = self.res(0x01, self._A[0])
        return 8
    
    # self.res 1, *
    def res1b(self):
        self._B[0] = self.res(0x02, self._B[0])
        return 8
    
    def res1c(self):
        self._C[0] = self.res(0x02, self._C[0])
        return 8
    
    def res1d(self):
        self._D[0] = self.res(0x02, self._D[0])
        return 8
    
    def res1e(self):
        self._E[0] = self.res(0x02, self._E[0])
        return 8
    
    def res1h(self):
        self._H[0] = self.res(0x02, self._H[0])
        return 8
    
    def res1l(self):
        self._L[0] = self.res(0x02, self._L[0])
        return 8
    
    def res1fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x02, self.memory.peekb(self._HL[0])))
        return 15
    
    def res1a(self):
        self._A[0] = self.res(0x02, self._A[0])
        return 8
    
    # self.res 2, *
    def res2b(self):
        self._B[0] = self.res(0x04, self._B[0])
        return 8
    
    def res2c(self):
        self._C[0] = self.res(0x04, self._C[0])
        return 8
    
    def res2d(self):
        self._D[0] = self.res(0x04, self._D[0])
        return 8
    
    def res2e(self):
        self._E[0] = self.res(0x04, self._E[0])
        return 8
    
    def res2h(self):
        self._H[0] = self.res(0x04, self._H[0])
        return 8
    
    def res2l(self):
        self._L[0] = self.res(0x04, self._L[0])
        return 8
    
    def res2fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x04, self.memory.peekb(self._HL[0])))
        return 15
    
    def res2a(self):
        self._A[0] = self.res(0x04, self._A[0])
        return 8
    
    # self.res 3, *
    def res3b(self):
        self._B[0] = self.res(0x08, self._B[0])
        return 8
    
    def res3c(self):
        self._C[0] = self.res(0x08, self._C[0])
        return 8
    
    def res3d(self):
        self._D[0] = self.res(0x08, self._D[0])
        return 8
    
    def res3e(self):
        self._E[0] = self.res(0x08, self._E[0])
        return 8
    
    def res3h(self):
        self._H[0] = self.res(0x08, self._H[0])
        return 8
    
    def res3l(self):
        self._L[0] = self.res(0x08, self._L[0])
        return 8
    
    def res3fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x08, self.memory.peekb(self._HL[0])))
        return 15
    
    def res3a(self):
        self._A[0] = self.res(0x08, self._A[0])
        return 8
    
    # self.res 4, *
    def res4b(self):
        self._B[0] = self.res(0x10, self._B[0])
        return 8
    
    def res4c(self):
        self._C[0] = self.res(0x10, self._C[0])
        return 8
    
    def res4d(self):
        self._D[0] = self.res(0x10, self._D[0])
        return 8
    
    def res4e(self):
        self._E[0] = self.res(0x10, self._E[0])
        return 8
    
    def res4h(self):
        self._H[0] = self.res(0x10, self._H[0])
        return 8
    
    def res4l(self):
        self._L[0] = self.res(0x10, self._L[0])
        return 8
    
    def res4fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x10, self.memory.peekb(self._HL[0])))
        return 15
    
    def res4a(self):
        self._A[0] = self.res(0x10, self._A[0])
        return 8
    
    # self.res 5, *
    def res5b(self):
        self._B[0] = self.res(0x20, self._B[0])
        return 8
    
    def res5c(self):
        self._C[0] = self.res(0x20, self._C[0])
        return 8
    
    def res5d(self):
        self._D[0] = self.res(0x20, self._D[0])
        return 8
    
    def res5e(self):
        self._E[0] = self.res(0x20, self._E[0])
        return 8
    
    def res5h(self):
        self._H[0] = self.res(0x20, self._H[0])
        return 8
    
    def res5l(self):
        self._L[0] = self.res(0x20, self._L[0])
        return 8
    
    def res5fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x20, self.memory.peekb(self._HL[0])))
        return 15
    
    def res5a(self):
        self._A[0] = self.res(0x20, self._A[0])
        return 8
    
    # self.res 6, *
    def res6b(self):
        self._B[0] = self.res(0x40, self._B[0])
        return 8
    
    def res6c(self):
        self._C[0] = self.res(0x40, self._C[0])
        return 8
    
    def res6d(self):
        self._D[0] = self.res(0x40, self._D[0])
        return 8
    
    def res6e(self):
        self._E[0] = self.res(0x40, self._E[0])
        return 8
    
    def res6h(self):
        self._H[0] = self.res(0x40, self._H[0])
        return 8
    
    def res6l(self):
        self._L[0] = self.res(0x40, self._L[0])
        return 8
    
    def res6fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x40, self.memory.peekb(self._HL[0])))
        return 15
    
    def res6a(self):
        self._A[0] = self.res(0x40, self._A[0])
        return 8
    
    # self.res 7, *
    def res7b(self):
        self._B[0] = self.res(0x80, self._B[0])
        return 8
    
    def res7c(self):
        self._C[0] = self.res(0x80, self._C[0])
        return 8
    
    def res7d(self):
        self._D[0] = self.res(0x80, self._D[0])
        return 8
    
    def res7e(self):
        self._E[0] = self.res(0x80, self._E[0])
        return 8
    
    def res7h(self):
        self._H[0] = self.res(0x80, self._H[0])
        return 8
    
    def res7l(self):
        self._L[0] = self.res(0x80, self._L[0])
        return 8
    
    def res7fromhl(self):
        self.memory.pokeb(self._HL[0], self.res(0x80, self.memory.peekb(self._HL[0])))
        return 15
    
    def res7a(self):
        self._A[0] = self.res(0x80, self._A[0])
        return 8
    
    # self.set 0, *
    def set0b(self):
        self._B[0] = self.set(0x01, self._B[0])
        return 8
    
    def set0c(self):
        self._C[0] = self.set(0x01, self._C[0])
        return 8
    
    def set0d(self):
        self._D[0] = self.set(0x01, self._D[0])
        return 8
    
    def set0e(self):
        self._E[0] = self.set(0x01, self._E[0])
        return 8
    
    def set0h(self):
        self._H[0] = self.set(0x01, self._H[0])
        return 8
    
    def set0l(self):
        self._L[0] = self.set(0x01, self._L[0])
        return 8
    
    def set0fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x01, self.memory.peekb(self._HL[0])))
        return 15
    
    def set0a(self):
        self._A[0] = self.set(0x01, self._A[0])
        return 8
    
    # self.set 1, *
    def set1b(self):
        self._B[0] = self.set(0x02, self._B[0])
        return 8
    
    def set1c(self):
        self._C[0] = self.set(0x02, self._C[0])
        return 8
    
    def set1d(self):
        self._D[0] = self.set(0x02, self._D[0])
        return 8
    
    def set1e(self):
        self._E[0] = self.set(0x02, self._E[0])
        return 8
    
    def set1h(self):
        self._H[0] = self.set(0x02, self._H[0])
        return 8
    
    def set1l(self):
        self._L[0] = self.set(0x02, self._L[0])
        return 8
    
    def set1fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x02, self.memory.peekb(self._HL[0])))
        return 15
    
    def set1a(self):
        self._A[0] = self.set(0x02, self._A[0])
        return 8
    
    # self.set 2, *
    def set2b(self):
        self._B[0] = self.set(0x04, self._B[0])
        return 8
    
    def set2c(self):
        self._C[0] = self.set(0x04, self._C[0])
        return 8
    
    def set2d(self):
        self._D[0] = self.set(0x04, self._D[0])
        return 8
    
    def set2e(self):
        self._E[0] = self.set(0x04, self._E[0])
        return 8
    
    def set2h(self):
        self._H[0] = self.set(0x04, self._H[0])
        return 8
    
    def set2l(self):
        self._L[0] = self.set(0x04, self._L[0])
        return 8
    
    def set2fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x04, self.memory.peekb(self._HL[0])))
        return 15
    
    def set2a(self):
        self._A[0] = self.set(0x04, self._A[0])
        return 8
    
    # self.set 3, *
    def set3b(self):
        self._B[0] = self.set(0x08, self._B[0])
        return 8
    
    def set3c(self):
        self._C[0] = self.set(0x08, self._C[0])
        return 8
    
    def set3d(self):
        self._D[0] = self.set(0x08, self._D[0])
        return 8
    
    def set3e(self):
        self._E[0] = self.set(0x08, self._E[0])
        return 8
    
    def set3h(self):
        self._H[0] = self.set(0x08, self._H[0])
        return 8
    
    def set3l(self):
        self._L[0] = self.set(0x08, self._L[0])
        return 8
    
    def set3fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x08, self.memory.peekb(self._HL[0])))
        return 15
    
    def set3a(self):
        self._A[0] = self.set(0x08, self._A[0])
        return 8
    
    # self.set 4, *
    def set4b(self):
        self._B[0] = self.set(0x10, self._B[0])
        return 8
    
    def set4c(self):
        self._C[0] = self.set(0x10, self._C[0])
        return 8
    
    def set4d(self):
        self._D[0] = self.set(0x10, self._D[0])
        return 8
    
    def set4e(self):
        self._E[0] = self.set(0x10, self._E[0])
        return 8
    
    def set4h(self):
        self._H[0] = self.set(0x10, self._H[0])
        return 8
    
    def set4l(self):
        self._L[0] = self.set(0x10, self._L[0])
        return 8
    
    def set4fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x10, self.memory.peekb(self._HL[0])))
        return 15
    
    def set4a(self):
        self._A[0] = self.set(0x10, self._A[0])
        return 8
    
    # self.set 5, *
    def set5b(self):
        self._B[0] = self.set(0x20, self._B[0])
        return 8
    
    def set5c(self):
        self._C[0] = self.set(0x20, self._C[0])
        return 8
    
    def set5d(self):
        self._D[0] = self.set(0x20, self._D[0])
        return 8
    
    def set5e(self):
        self._E[0] = self.set(0x20, self._E[0])
        return 8
    
    def set5h(self):
        self._H[0] = self.set(0x20, self._H[0])
        return 8
    
    def set5l(self):
        self._L[0] = self.set(0x20, self._L[0])
        return 8
    
    def set5fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x20, self.memory.peekb(self._HL[0])))
        return 15
    
    def set5a(self):
        self._A[0] = self.set(0x20, self._A[0])
        return 8
    
    # self.set 6, *
    def set6b(self):
        self._B[0] = self.set(0x40, self._B[0])
        return 8
    
    def set6c(self):
        self._C[0] = self.set(0x40, self._C[0])
        return 8
    
    def set6d(self):
        self._D[0] = self.set(0x40, self._D[0])
        return 8
    
    def set6e(self):
        self._E[0] = self.set(0x40, self._E[0])
        return 8
    
    def set6h(self):
        self._H[0] = self.set(0x40, self._H[0])
        return 8
    
    def set6l(self):
        self._L[0] = self.set(0x40, self._L[0])
        return 8
    
    def set6fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x40, self.memory.peekb(self._HL[0])))
        return 15
    
    def set6a(self):
        self._A[0] = self.set(0x40, self._A[0])
        return 8
    
    # self.set 7, *
    def set7b(self):
        self._B[0] = self.set(0x80, self._B[0])
        return 8
    
    def set7c(self):
        self._C[0] = self.set(0x80, self._C[0])
        return 8
    
    def set7d(self):
        self._D[0] = self.set(0x80, self._D[0])
        return 8
    
    def set7e(self):
        self._E[0] = self.set(0x80, self._E[0])
        return 8
    
    def set7h(self):
        self._H[0] = self.set(0x80, self._H[0])
        return 8
    
    def set7l(self):
        self._L[0] = self.set(0x80, self._L[0])
        return 8
    
    def set7fromhl(self):
        self.memory.pokeb(self._HL[0], self.set(0x80, self.memory.peekb(self._HL[0])))
        return 15
    
    def set7a(self):
        self._A[0] = self.set(0x80, self._A[0])
        return 8
    
    def cb(self):
        self.inc_r()
        opcode = (self.nxtpcb())
        return self._cbdict.get(opcode)()
    
    def outna(self):
        self.ports.port_out(self.nxtpcb(), self._A[0])
        return 11
    
    def inan(self):
        self._A[0] = self.ports.port_in(self._A[0] << 8 | self.nxtpcb())
        return 11
    
    def exsphl(self):
        t = self._HL[0]
        self._HL[0] = self.memory.peekw(self._SP[0])
        self.memory.pokew(self._SP[0], t)
        return 19
    
    def exdehl(self):
        self._HL[0], self._DE[0] = self._DE[0], self._HL[0]
        return 4
    
    def di(self):
        self._IFF1 = False
        self._IFF2 = False
        return 4
    
    def ei(self):
        self._IFF1 = True
        self._IFF2 = True
        return 4
    
    # CALL cc,nn
    def callnznn(self):
        if not self._fZ:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callznn(self):
        if self._fZ:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callncnn(self):
        if not self._fC:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callcnn(self):
        if self._fC:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callponn(self):
        if not self._fPV:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callpenn(self):
        if self._fPV:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callpnn(self):
        if not self._fS:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    def callmnn(self):
        if self._fS:
            t = self.nxtpcw()
            self.pushpc()
            self._PC[0] = t
            return 17
        else:
            self._PC[0] = (self._PC[0] + 2) % 65536
            return 10
    
    # PUSH
    def pushbc(self):
        self.pushw(self._BC[0])
        return 11
    
    def pushde(self):
        self.pushw(self._DE[0])
        return 11
    
    def pushhl(self):
        self.pushw(self._HL[0])
        return 11
    
    def pushaf(self):
        self._F[0] = (F_S if self._fS else 0) + \
            (F_Z if self._fZ else 0) + \
            (F_5 if self._f5 else 0) + \
            (F_H if self._fH else 0) + \
            (F_3 if self._f3 else 0) + \
            (F_PV if self._fPV else 0) + \
            (F_N if self._fN else 0) + \
            (F_C if self._fC else 0)
        self.pushw(self._AF[0])
        return 11
    
    # op A,N
    def addan(self):
        self.add_a(self.nxtpcb())
        return 7
    
    def adcan(self):
        self.adc_a(self.nxtpcb())
        return 7
    
    def suban(self):
        self.sub_a(self.nxtpcb())
        return 7
    
    def sbcan(self):
        self.sbc_a(self.nxtpcb())
        return 7
    
    def andan(self):
        self.and_a(self.nxtpcb())
        return 7
    
    def xoran(self):
        self.xor_a(self.nxtpcb())
        return 7
    
    def oran(self):
        self.or_a(self.nxtpcb())
        return 7
    
    def cpan(self):
        self.cp_a(self.nxtpcb())
        return 7
    
    # RST n
    def rst0(self):
        self.pushpc()
        self._PC[0] = 0
        return 11
    
    def rst8(self):
        self.pushpc()
        self._PC[0] = 8
        return 11
    
    def rst16(self):
        self.pushpc()
        self._PC[0] = 16
        return 11
    
    def rst24(self):
        self.pushpc()
        self._PC[0] = 24
        return 11
    
    def rst32(self):
        self.pushpc()
        self._PC[0] = 32
        return 11
    
    def rst40(self):
        self.pushpc()
        self._PC[0] = 40
        return 11
    
    def rst48(self):
        self.pushpc()
        self._PC[0] = 48
        return 11
    
    def rst56(self):
        self.pushpc()
        self._PC[0] = 56
        return 11
    
    # Various
    def callnn(self):
        t = self.nxtpcw()
        self.pushpc()
        self._PC[0] = t
        return 17
    
    def ix(self):
        self.inc_r()
        self._ID = self._IX
        self._IDL = self._IXL
        self._IDH = self._IXH
        return self.execute_id()
    
    # ED prefix
    # IN r,(c)
    def inbfrombc(self):
        self._B[0] = self.in_bc()
        return 12
    
    def incfrombc(self):
        self._C[0] = self.in_bc()
        return 12
    
    def indfrombc(self):
        self._D[0] = self.in_bc()
        return 12
    
    def inefrombc(self):
        self._E[0] = self.in_bc()
        return 12
    
    def inhfrombc(self):
        self._H[0] = self.in_bc()
        return 12
    
    def inlfrombc(self):
        self._L[0] = self.in_bc()
        return 12
    
    def infrombc(self):
        self.in_bc()
        return 12
    
    def inafrombc(self):
        self._A[0] = self.in_bc()
        return 12
    
    # OUT (c),r
    def outtocb(self):
        self.ports.port_out(self._BC[0], self._B[0])
        return 12
    
    def outtocc(self):
        self.ports.port_out(self._BC[0], self._C[0])
        return 12
    
    def outtocd(self):
        self.ports.port_out(self._BC[0], self._D[0])
        return 12
    
    def outtoce(self):
        self.ports.port_out(self._BC[0], self._E[0])
        return 12
    
    def outtoch(self):
        self.ports.port_out(self._BC[0], self._H[0])
        return 12
    
    def outtocl(self):
        self.ports.port_out(self._BC[0], self._L[0])
        return 12
    
    def outtoc0(self):
        self.ports.port_out(self._BC[0], 0)
        return 12
    
    def outtoca(self):
        self.ports.port_out(self._BC[0], self._A[0])
        return 12
    
    # SBC/ADC HL,ss
    def sbchlbc(self):
        self._HL[0] = self.sbc16(self._HL[0], self._BC[0])
        return 15
    
    def adchlbc(self):
        self._HL[0] = self.adc16(self._HL[0], self._BC[0])
        return 15
    
    def sbchlde(self):
        self._HL[0] = self.sbc16(self._HL[0], self._DE[0])
        return 15
    
    def adchlde(self):
        self._HL[0] = self.adc16(self._HL[0], self._DE[0])
        return 15
    
    def sbchlhl(self):
        hl = self._HL[0]
        self._HL[0] = self.sbc16(hl, hl)
        return 15
    
    def adchlhl(self):
        hl = self._HL[0]
        self._HL[0] = self.adc16(hl, hl)
        return 15
    
    def sbchlsp(self):
        self._HL[0] = self.sbc16(self._HL[0], self._SP[0])
        return 15
    
    def adchlsp(self):
        self._HL[0] = self.adc16(self._HL[0], self._SP[0])
        return 15
    
    # LD (nn),ss, LD ss,(nn)
    def ldtonnbc(self):
        self.memory.pokew(self.nxtpcw(), self._BC[0])
        return 20
    
    def ldbcfromnn(self):
        self._BC[0] = self.memory.peekw(self.nxtpcw())
        return 20
    
    def ldtonnde(self):
        self.memory.pokew(self.nxtpcw(), self._DE[0])
        return 20
    
    def lddefromnn(self):
        self._DE[0] = self.memory.peekw(self.nxtpcw())
        return 20
    
    def edldtonnhl(self):
        return self.ldtonnhl() + 4
    
    def edldhlfromnn(self):
        return self.ldhlfromnn() + 4
    
    def ldtonnsp(self):
        self.memory.pokew(self.nxtpcw(), self._SP[0])
        return 20
    
    def ldspfromnn(self):
        self._SP[0] = self.memory.peekw(self.nxtpcw())
        return 20
    
    # NEG
    def nega(self):
        t = self._A[0]
        self._A[0] = 0
        self.sub_a(t)
        self._fPV = t == 0x80
        self._fC = t != 0
        return 8
    
    # RETn
    def retn(self):
        self._IFF1 = self._IFF2
        self.poppc()
        return 14
    
    def reti(self):
        self.poppc()
        return 14
    
    # IM x
    def im0(self):
        self._IM = IM0
        return 8
    
    def im1(self):
        self._IM = IM1
        return 8
    
    def im2(self):
        self._IM = IM2
        return 8
    
    # LD A,s / LD s,A / RxD
    def ldia(self):
        self._I[0] = self._A[0]
        return 9
    
    def ldra(self):
        self._R = self._A[0]
        return 9
    
    def ldai(self):
        ans = self._I[0]
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = ans == 0
        self._fPV = self._IFF2
        self._fH = False
        self._fN = False
        self._A[0] = ans
        return 9
    
    # Load a with r - (NOT CHECKED)
    def ldar(self):
        self._A[0] = self._R
        self._fS = self._A[0] > 0x7f
        self._f3 = (self._A[0] & F_3) != 0
        _f5 = (self._A[0] & F_5) != 0
        self._fZ = self._A[0] == 0
        self._fPV = self._IFF2
        self._fH = False
        self._fN = False
        return 9
    
    def rrda(self):
        ans = self._A[0]
        t = self.memory.peekb(self._HL[0])
        q = t
    
        t = ((t >> 4) + (ans << 4)) % 256
        ans = (ans & 0xf0) + (q % 16)
        self.memory.pokeb(self._HL[0], t)
        self._fS = (ans & F_S) != 0
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = ans == 0
        self._fPV = self.parity[ans]
        self._fH = False
        self._fN = False
        self._A[0] = ans
        return 18
    
    def rlda(self):
        ans = self._A[0]
        t = self.memory.peekb(self._HL[0])
        q = t
    
        t = ((t << 4) + (ans % 16)) % 256
        ans = ((ans & 0xf0) + (q >> 4)) % 256
        self.memory.pokeb(self._HL[0], t)
        self._fS = (ans & F_S) != 0
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = ans == 0
        self._fPV = self.parity[ans]
        self._fH = False
        self._fN = False
        self._A[0] = ans
        return 18
    
    # xxI
    def ldi(self):
        self.memory.pokeb(self._DE[0], self.memory.peekb(self._HL[0]))
        self._DE[0] = self.inc16(self._DE[0])
        self._HL[0] = self.inc16(self._HL[0])
        self._BC[0] = self.dec16(self._BC[0])
        self._fPV = self._BC[0] != 0
        self._fH = False
        self._fN = False
        return 16
    
    def cpi(self):
        c = self._fC
        self.cp_a(self.memory.peekb(self._HL[0]))
        self._HL[0] = self.inc16(self._HL[0])
        self._BC[0] = self.dec16(self._BC[0])
        self._fPV = self._BC[0] != 0
        self._fC = c
        self._fN = True
        return 16
    
    def ini(self):
        c = self._fC
        self.memory.pokeb(self._HL[0], self.ports.port_in(self._BC[0]))
        self._HL[0] = self.inc16(self._HL[0])
        self._B[0] = self.qdec8(self._B[0])
        self._fC = c
        self._fN = False
        self._fZ = self._B[0] == 0
        return 16
    
    def outi(self):
        c = self._fC
        self.ports.port_out(self._BC[0], self.memory.peekb(self._HL[0]))
        self._HL[0] = self.inc16(self._HL[0])
        self._B[0] = self.qdec8(self._B[0])
        self._fC = c
        self._fN = False
        self._fZ = self._B[0] == 0
        return 16
    
    # xxD
    def ldd(self):
        self.memory.pokeb(self._DE[0], self.memory.peekb(self._HL[0]))
        self._DE[0] = self.dec16(self._DE[0])
        self._HL[0] = self.dec16(self._HL[0])
        self._BC[0] = self.dec16(self._BC[0])
        self._fPV = self._BC[0] != 0
        self._fH = False
        self._fN = False
        return 16
    
    def cpd(self):
        c = self._fC
        self.cp_a(self.memory.peekb(self._HL[0]))
        self._HL[0] = self.dec16(self._HL[0])
        self._BC[0] = self.dec16(self._BC[0])
        self._fC = c
        self._fN = True
        self._fPV = self._BC[0] != 0
        return 16
    
    def ind(self):
        self.memory.pokeb(self._HL[0], self.ports.port_in(self._BC[0]))
        self._HL[0] = self.dec16(self._HL[0])
        self._B[0] = self.qdec8(self._B[0])
        self._fN = True
        self._fZ = self._B[0] == 0
        return 16
    
    def outd(self):
        self.ports.port_out(self._BC[0], self.memory.peekb(self._HL[0]))
        self._HL[0] = self.dec16(self._HL[0])
        self._B[0] = self.qdec8(self._B[0])
        self._fN = True
        self._fZ = self._B[0] == 0
        return 16
    
    # xxIR
    def ldir(self):
        self._fPV = True
        while True:
            self.memory.pokeb(self._DE[0], self.memory.peekb(self._HL[0]))
            self._DE[0] = (self._DE[0] + 1) % 65536
            self._HL[0] = (self._HL[0] + 1) % 65536
            self._BC[0] = (self._BC[0] - 1) % 65536
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._BC[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fPV = False
        self._fN = False
        self._fH = False
        return 16
    
    def cpir(self):
        c = self._fC
        self._fPV = True
        while True:
            self.cp_a(self.memory.peekb(self._HL[0]))
            self._HL[0] = (self._HL[0] + 1) % 65536
            self._BC[0] = (self._BC[0] - 1) % 65536
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._BC[0] == 0 or self._fZ:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fC = c
        self._fN = True
        self._fPV = self._BC[0] != 0
        return 16
    
    def inir(self):
        while True:
            self.memory.pokeb(self._HL, self.ports.port_in(self._BC[0]))
            self._HL[0] = (self._HL[0] + 1) % 65536
            self._B[0] = (self._B[0] - 1) % 256
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._B[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fZ = True
        self._fC = False
        self._fN = False
        return 16
    
    def otir(self):
        while True:
            self.ports.port_out(self._BC[0], self.memory.peekb(self._HL[0]))
            self._HL[0] = (self._HL[0] + 1) % 65536
            self._B[0] = (self._B[0] - 1) % 256
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._B[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fZ = True
        self._fN = False
        return 16
    
    # xxDR
    def lddr(self):
        self._fPV = True
        while True:
            self.memory.pokeb(self._DE[0], self.memory.peekb(self._HL[0]))
            self._DE[0] = (self._DE[0] - 1) % 65536
            self._HL[0] = (self._HL[0] - 1) % 65536
            self._BC[0] = (self._BC[0] - 1) % 65536
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._BC[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fPV = False
        self._fH = False
        self._fN = False
        return 16
    
    def cpdr(self):
        c = self._fC
        self._fPV = True
        while True:
            self.cp_a(self.memory.peekb(self._HL[0]))
            self._HL[0] = (self._HL[0] - 1) % 65536
            self._BC[0] = (self._BC[0] - 1) % 65536
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._BC[0] == 0 or self._fZ:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fC = c
        self._fN = True
        self._fPV = self._BC[0] != 0
        return 16
    
    def indr(self):
        while True:
            self.memory.pokeb(self._HL, self.ports.port_in(self._BC[0]))
            self._HL[0] = (self._HL[0] - 1) % 65536
            self._B[0] = (self._B[0] - 1) % 256
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._B[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fZ = True
        self._fC = False
        self._fN = False
        return 16
    
    def otdr(self):
        while True:
            self.ports.port_out(self._BC[0], self.memory.peekb(self._HL[0]))
            self._HL[0] = (self._HL[0] - 1) % 65536
            self._B[0] = (self._B[0] - 1) % 256
            self._R_b[0] = (self._R_b[0] + 2) % 128 + self._R7_b
            if self._B[0] == 0:
                break
            self.local_clock_cycles_counter += 21
            self.clock_cycle_test(self)
        self._fZ = True
        self._fN = False
        return 16
    
    @staticmethod
    def ednop():
        return 8
    
    def ed(self):
        opcode = self.nxtpcb()
        return self._eddict.get(opcode, self.ednop)()
    
    def iy(self):
        self.inc_r()
        self._ID = self._IY
        self._IDL = self._IYL
        self._IDH = self._IYH
        return self.execute_id()

    # IX, IY ops
    # ADD ID, *
    def addidbc(self):
        self._ID[0] = self.add16(self._ID[0], self._BC[0])
        return 15
    
    def addidde(self):
        self._ID[0] = self.add16(self._ID[0], self._DE[0])
        return 15
    
    def addidid(self):
        _id = self._ID[0]
        self._ID[0] = self.add16(_id, _id)
        return 15
    
    def addidsp(self):
        self._ID[0] = self.add16(self._ID[0], self._SP[0])
        return 15
    
    # LD ID, nn
    def ldidnn(self):
        self._ID[0] = self.nxtpcw()
        return 14
    
    def ldtonnid(self):
        self.memory.pokew(self.nxtpcw(), self._ID[0])
        return 20
    
    def ldidfromnn(self):
        self._ID[0] = self.memory.peekw(self.nxtpcw())
        return 20
    
    # INC
    def incid(self):
        self._ID[0] = self.inc16(self._ID[0])
        return 10
    
    def incidh(self):
        self._IDH[0] = self.inc8(self._IDH[0])
        return 8
    
    def incidl(self):
        self._IDL[0] = self.inc8(self._IDL[0])
        return 8
    
    def incinidd(self):
        z = self.ID_d()
        self.memory.pokeb(z, self.inc8(self.memory.peekb(z)))
        return 23

    # DEC
    def decid(self):
        self._ID[0] = self.dec16(self._ID[0])
        return 10
    
    def decidh(self):
        self._IDH[0] = self.dec8(self._IDH[0])
        return 8
    
    def decidl(self):
        self._IDL[0] = self.dec8(self._IDL[0])
        return 8
    
    def decinidd(self):
        z = self.ID_d()
        self.memory.pokeb(z, self.dec8(self.memory.peekb(z)))
        return 23
    
    # LD *, IDH
    def ldbidh(self):
        self._B[0] = self._IDH[0]
        return 8
    
    def ldcidh(self):
        self._C[0] = self._IDH[0]
        return 8
    
    def lddidh(self):
        self._D[0] = self._IDH[0]
        return 8
    
    def ldeidh(self):
        self._E[0] = self._IDH[0]
        return 8
    
    def ldaidh(self):
        self._A[0] = self._IDH[0]
        return 8
    
    # LD *, IDL
    def ldbidl(self):
        self._B[0] = self._IDL[0]
        return 8
    
    def ldcidl(self):
        self._C[0] = self._IDL[0]
        return 8
    
    def lddidl(self):
        self._D[0] = self._IDL[0]
        return 8
    
    def ldeidl(self):
        self._E[0] = self._IDL[0]
        return 8
    
    def ldaidl(self):
        self._A[0] = self._IDL[0]
        return 8
    
    # LD IDH, *
    def ldidhb(self):
        self._IDH[0] = self._B[0]
        return 8
    
    def ldidhc(self):
        self._IDH[0] = self._C[0]
        return 8
    
    def ldidhd(self):
        self._IDH[0] = self._D[0]
        return 8
    
    def ldidhe(self):
        self._IDH[0] = self._E[0]
        return 8
    
    @staticmethod
    def ldidhidh():
        return 8
    
    def ldidhidl(self):
        self._IDH[0] = self._IDL[0]
        return 8
    
    def ldidhn(self):
        self._IDH[0] = self.nxtpcb()
        return 11
    
    def ldidha(self):
        self._IDH[0] = self._A[0]
        return 8
    
    # LD IDL, *
    def ldidlb(self):
        self._IDL[0] = self._B[0]
        return 8
    
    def ldidlc(self):
        self._IDL[0] = self._C[0]
        return 8
    
    def ldidld(self):
        self._IDL[0] = self._D[0]
        return 8
    
    def ldidle(self):
        self._IDL[0] = self._E[0]
        return 8
    
    def ldidlidh(self):
        self._IDL[0] = self._IDH[0]
        return 8
    
    @staticmethod
    def ldidlidl():
        return 8
    
    def ldidln(self):
        self._IDL[0] = self.nxtpcb()
        return 11
    
    def ldidla(self):
        self._IDL[0] = self._A[0]
        return 8
    
    # LD *, (ID+d)
    def ldbfromidd(self):
        self._B[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def ldcfromidd(self):
        self._C[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def lddfromidd(self):
        self._D[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def ldefromidd(self):
        self._E[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def ldhfromidd(self):
        self._H[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def ldlfromidd(self):
        self._L[0] = self.memory.peekb(self.ID_d())
        return 19
    
    def ldafromidd(self):
        self._A[0] = self.memory.peekb(self.ID_d())
        return 19
    
    # LD (ID+d), *
    def ldtoiddb(self):
        self.memory.pokeb(self.ID_d(), self._B[0])
        return 19
    
    def ldtoiddc(self):
        self.memory.pokeb(self.ID_d(), self._C[0])
        return 19
    
    def ldtoiddd(self):
        self.memory.pokeb(self.ID_d(), self._D[0])
        return 19
    
    def ldtoidde(self):
        self.memory.pokeb(self.ID_d(), self._E[0])
        return 19
    
    def ldtoiddh(self):
        self.memory.pokeb(self.ID_d(), self._H[0])
        return 19
    
    def ldtoiddl(self):
        self.memory.pokeb(self.ID_d(), self._L[0])
        return 19
    
    def ldtoiddn(self):
        self.memory.pokeb(self.ID_d(), self.nxtpcb())
        return 19
    
    def ldtoidda(self):
        self.memory.pokeb(self.ID_d(), self._A[0])
        return 19
    
    # ADD/ADC A, *
    def addaidh(self):
        self.add_a(self._IDH[0])
        return 8
    
    def addaidl(self):
        self.add_a(self._IDL[0])
        return 8
    
    def addafromidd(self):
        self.add_a(self.memory.peekb(self.ID_d()))
        return 19
    
    def adcaidh(self):
        self.adc_a(self._IDH[0])
        return 8
    
    def adcaidl(self):
        self.adc_a(self._IDL[0])
        return 8
    
    def adcafromidd(self):
        self.adc_a(self.memory.peekb(self.ID_d()))
        return 19
    
    # SUB/SBC A, *
    def subaidh(self):
        self.sub_a(self._IDH[0])
        return 8
    
    def subaidl(self):
        self.sub_a(self._IDL[0])
        return 8
    
    def subafromidd(self):
        self.sub_a(self.memory.peekb(self.ID_d()))
        return 19
    
    def sbcaidh(self):
        self.sbc_a(self._IDH[0])
        return 8
    
    def sbcaidl(self):
        self.sbc_a(self._IDL[0])
        return 8
    
    def sbcafromidd(self):
        self.sbc_a(self.memory.peekb(self.ID_d()))
        return 19
    
    # Bitwise OPS
    def andaidh(self):
        self.and_a(self._IDH[0])
        return 8
    
    def andaidl(self):
        self.and_a(self._IDL[0])
        return 8
    
    def andafromidd(self):
        self.and_a(self.memory.peekb(self.ID_d()))
        return 19
    
    def xoraidh(self):
        self.xor_a(self._IDH[0])
        return 8
    
    def xoraidl(self):
        self.xor_a(self._IDL[0])
        return 8
    
    def xorafromidd(self):
        self.xor_a(self.memory.peekb(self.ID_d()))
        return 19
    
    def oraidh(self):
        self.or_a(self._IDH[0])
        return 8
    
    def oraidl(self):
        self.or_a(self._IDL[0])
        return 8
    
    def orafromidd(self):
        self.or_a(self.memory.peekb(self.ID_d()))
        return 19
    
    # CP A, *
    def cpaidh(self):
        self.cp_a(self._IDH[0])
        return 8
    
    def cpaidl(self):
        self.cp_a(self._IDL[0])
        return 8
    
    def cpafromidd(self):
        self.cp_a(self.memory.peekb(self.ID_d()))
        return 19
    
    # Various
    def pushid(self):
        self.pushw(self._ID[0])
        return 15
    
    def popid(self):
        self._ID[0] = self.popw()
        return 14
    
    def jpid(self):
        self._PC[0] = self._ID[0]
        return 8
    
    def ldspid(self):
        self._SP[0] = self._ID[0]
        return 10
    
    def exfromspid(self):
        t = self._ID[0]
        sp = self._SP[0]
        self._ID[0] = self.memory.peekw(sp)
        self.memory.pokew(sp, t)
        return 23
    
    # DDCB/FDCB prefix
    def idcb(self):
        # Get index address (offset byte is first)
        z = self.ID_d()
        # Opcode comes after offset byte
        op = self.nxtpcb()
        return self.execute_id_cb(op, z)
    
    def ID_d(self):
        return (self._ID[0] + self.nxtpcsb()) % 65536
    
    # DDCB/FDCB opcodes
    # self.rlc *
    def cbrlcb(self, z):
        self._B[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbrlcc(self, z):
        self._C[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbrlcd(self, z):
        self._D[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbrlce(self, z):
        self._E[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbrlch(self, z):
        self._H[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbrlcl(self, z):
        self._L[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbrlcinhl(self, z):
        self.memory.pokeb(z, self.rlc(self.memory.peekb(z)))
        return 23
    
    def cbrlca(self, z):
        self._A[0] = self.rlc(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.rrc *
    def cbrrcb(self, z):
        self._B[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbrrcc(self, z):
        self._C[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbrrcd(self, z):
        self._D[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbrrce(self, z):
        self._E[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbrrch(self, z):
        self._H[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbrrcl(self, z):
        self._L[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbrrcinhl(self, z):
        self.memory.pokeb(z, self.rrc(self.memory.peekb(z)))
        return 23
    
    def cbrrca(self, z):
        self._A[0] = self.rrc(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.rl *
    def cbrlb(self, z):
        self._B[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbrlc(self, z):
        self._C[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbrld(self, z):
        self._D[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbrle(self, z):
        self._E[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbrlh(self, z):
        self._H[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbrll(self, z):
        self._L[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbrlinhl(self, z):
        self.memory.pokeb(z, self.rl(self.memory.peekb(z)))
        return 23
    
    def cbrla(self, z):
        self._A[0] = self.rl(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.rr *
    def cbrrb(self, z):
        self._B[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbrrc(self, z):
        self._C[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbrrd(self, z):
        self._D[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbrre(self, z):
        self._E[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbrrh(self, z):
        self._H[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbrrl(self, z):
        self._L[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbrrinhl(self, z):
        self.memory.pokeb(z, self.rr(self.memory.peekb(z)))
        return 23
    
    def cbrra(self, z):
        self._A[0] = self.rr(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.sla *
    def cbslab(self, z):
        self._B[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbslac(self, z):
        self._C[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbslad(self, z):
        self._D[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbslae(self, z):
        self._E[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbslah(self, z):
        self._H[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbslal(self, z):
        self._L[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbslainhl(self, z):
        self.memory.pokeb(z, self.sla(self.memory.peekb(z)))
        return 23
    
    def cbslaa(self, z):
        self._A[0] = self.sla(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.sra *
    def cbsrab(self, z):
        self._B[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbsrac(self, z):
        self._C[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbsrad(self, z):
        self._D[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbsrae(self, z):
        self._E[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbsrah(self, z):
        self._H[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbsral(self, z):
        self._L[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbsrainhl(self, z):
        self.memory.pokeb(z, self.sra(self.memory.peekb(z)))
        return 23
    
    def cbsraa(self, z):
        self._A[0] = self.sra(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.sls *
    def cbslsb(self, z):
        self._B[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbslsc(self, z):
        self._C[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbslsd(self, z):
        self._D[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbslse(self, z):
        self._E[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbslsh(self, z):
        self._H[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbslsl(self, z):
        self._L[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbslsinhl(self, z):
        self.memory.pokeb(z, self.sls(self.memory.peekb(z)))
        return 23
    
    def cbslsa(self, z):
        self._A[0] = self.sls(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.srl *
    def cbsrlb(self, z):
        self._B[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbsrlc(self, z):
        self._C[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbsrld(self, z):
        self._D[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbsrle(self, z):
        self._E[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbsrlh(self, z):
        self._H[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbsrll(self, z):
        self._L[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbsrlinhl(self, z):
        self.memory.pokeb(z, self.srl(self.memory.peekb(z)))
        return 23
    
    def cbsrla(self, z):
        self._A[0] = self.srl(self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.bit *
    def cbbit0(self, z):
        self.bit(0x01, self.memory.peekb(z))
        return 20
    
    def cbbit1(self, z):
        self.bit(0x02, self.memory.peekb(z))
        return 20
    
    def cbbit2(self, z):
        self.bit(0x04, self.memory.peekb(z))
        return 20
    
    def cbbit3(self, z):
        self.bit(0x08, self.memory.peekb(z))
        return 20
    
    def cbbit4(self, z):
        self.bit(0x10, self.memory.peekb(z))
        return 20
    
    def cbbit5(self, z):
        self.bit(0x20, self.memory.peekb(z))
        return 20
    
    def cbbit6(self, z):
        self.bit(0x40, self.memory.peekb(z))
        return 20
    
    def cbbit7(self, z):
        self.bit(0x80, self.memory.peekb(z))
        return 20
    
    # self.res 0, *
    def cbres0b(self, z):
        self._B[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres0c(self, z):
        self._C[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres0d(self, z):
        self._D[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres0e(self, z):
        self._E[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres0h(self, z):
        self._H[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres0l(self, z):
        self._L[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres0inhl(self, z):
        self.memory.pokeb(z, self.res(0x01, self.memory.peekb(z)))
        return 23
    
    def cbres0a(self, z):
        self._A[0] = self.res(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 1, *
    def cbres1b(self, z):
        self._B[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres1c(self, z):
        self._C[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres1d(self, z):
        self._D[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres1e(self, z):
        self._E[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres1h(self, z):
        self._H[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres1l(self, z):
        self._L[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres1inhl(self, z):
        self.memory.pokeb(z, self.res(0x02, self.memory.peekb(z)))
        return 23
    
    def cbres1a(self, z):
        self._A[0] = self.res(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 2, *
    def cbres2b(self, z):
        self._B[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres2c(self, z):
        self._C[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres2d(self, z):
        self._D[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres2e(self, z):
        self._E[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres2h(self, z):
        self._H[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres2l(self, z):
        self._L[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres2inhl(self, z):
        self.memory.pokeb(z, self.res(0x04, self.memory.peekb(z)))
        return 23
    
    def cbres2a(self, z):
        self._A[0] = self.res(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 3, *
    def cbres3b(self, z):
        self._B[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres3c(self, z):
        self._C[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres3d(self, z):
        self._D[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres3e(self, z):
        self._E[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres3h(self, z):
        self._H[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres3l(self, z):
        self._L[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres3inhl(self, z):
        self.memory.pokeb(z, self.res(0x08, self.memory.peekb(z)))
        return 23
    
    def cbres3a(self, z):
        self._A[0] = self.res(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 4, *
    def cbres4b(self, z):
        self._B[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres4c(self, z):
        self._C[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres4d(self, z):
        self._D[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres4e(self, z):
        self._E[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres4h(self, z):
        self._H[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres4l(self, z):
        self._L[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres4inhl(self, z):
        self.memory.pokeb(z, self.res(0x10, self.memory.peekb(z)))
        return 23
    
    def cbres4a(self, z):
        self._A[0] = self.res(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 5, *
    def cbres5b(self, z):
        self._B[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres5c(self, z):
        self._C[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres5d(self, z):
        self._D[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres5e(self, z):
        self._E[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres5h(self, z):
        self._H[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres5l(self, z):
        self._L[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres5inhl(self, z):
        self.memory.pokeb(z, self.res(0x20, self.memory.peekb(z)))
        return 23
    
    def cbres5a(self, z):
        self._A[0] = self.res(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 6, *
    def cbres6b(self, z):
        self._B[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres6c(self, z):
        self._C[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres6d(self, z):
        self._D[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres6e(self, z):
        self._E[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres6h(self, z):
        self._H[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres6l(self, z):
        self._L[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres6inhl(self, z):
        self.memory.pokeb(z, self.res(0x40, self.memory.peekb(z)))
        return 23
    
    def cbres6a(self, z):
        self._A[0] = self.res(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.res 7, *
    def cbres7b(self, z):
        self._B[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbres7c(self, z):
        self._C[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbres7d(self, z):
        self._D[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbres7e(self, z):
        self._E[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbres7h(self, z):
        self._H[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbres7l(self, z):
        self._L[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbres7inhl(self, z):
        self.memory.pokeb(z, self.res(0x80, self.memory.peekb(z)))
        return 23
    
    def cbres7a(self, z):
        self._A[0] = self.res(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 0, *
    def cbset0b(self, z):
        self._B[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset0c(self, z):
        self._C[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset0d(self, z):
        self._D[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset0e(self, z):
        self._E[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset0h(self, z):
        self._H[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset0l(self, z):
        self._L[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset0inhl(self, z):
        self.memory.pokeb(z, self.set(0x01, self.memory.peekb(z)))
        return 23
    
    def cbset0a(self, z):
        self._A[0] = self.set(0x01, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 1, *
    def cbset1b(self, z):
        self._B[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset1c(self, z):
        self._C[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset1d(self, z):
        self._D[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset1e(self, z):
        self._E[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset1h(self, z):
        self._H[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset1l(self, z):
        self._L[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset1inhl(self, z):
        self.memory.pokeb(z, self.set(0x02, self.memory.peekb(z)))
        return 23
    
    def cbset1a(self, z):
        self._A[0] = self.set(0x02, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 2, *
    def cbset2b(self, z):
        self._B[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset2c(self, z):
        self._C[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset2d(self, z):
        self._D[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset2e(self, z):
        self._E[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset2h(self, z):
        self._H[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset2l(self, z):
        self._L[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset2inhl(self, z):
        self.memory.pokeb(z, self.set(0x04, self.memory.peekb(z)))
        return 23
    
    def cbset2a(self, z):
        self._A[0] = self.set(0x04, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 3, *
    def cbset3b(self, z):
        self._B[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset3c(self, z):
        self._C[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset3d(self, z):
        self._D[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset3e(self, z):
        self._E[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset3h(self, z):
        self._H[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset3l(self, z):
        self._L[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset3inhl(self, z):
        self.memory.pokeb(z, self.set(0x08, self.memory.peekb(z)))
        return 23
    
    def cbset3a(self, z):
        self._A[0] = self.set(0x08, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 4, *
    def cbset4b(self, z):
        self._B[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset4c(self, z):
        self._C[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset4d(self, z):
        self._D[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset4e(self, z):
        self._E[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset4h(self, z):
        self._H[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset4l(self, z):
        self._L[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset4inhl(self, z):
        self.memory.pokeb(z, self.set(0x10, self.memory.peekb(z)))
        return 23
    
    def cbset4a(self, z):
        self._A[0] = self.set(0x10, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 5, *
    def cbset5b(self, z):
        self._B[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset5c(self, z):
        self._C[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset5d(self, z):
        self._D[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset5e(self, z):
        self._E[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset5h(self, z):
        self._H[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset5l(self, z):
        self._L[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset5inhl(self, z):
        self.memory.pokeb(z, self.set(0x20, self.memory.peekb(z)))
        return 23
    
    def cbset5a(self, z):
        self._A[0] = self.set(0x20, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 6, *
    def cbset6b(self, z):
        self._B[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset6c(self, z):
        self._C[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset6d(self, z):
        self._D[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset6e(self, z):
        self._E[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset6h(self, z):
        self._H[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset6l(self, z):
        self._L[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset6inhl(self, z):
        self.memory.pokeb(z, self.set(0x40, self.memory.peekb(z)))
        return 23
    
    def cbset6a(self, z):
        self._A[0] = self.set(0x40, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23
    
    # self.set 7, *
    def cbset7b(self, z):
        self._B[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._B[0])
        return 23
    
    def cbset7c(self, z):
        self._C[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._C[0])
        return 23
    
    def cbset7d(self, z):
        self._D[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._D[0])
        return 23
    
    def cbset7e(self, z):
        self._E[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._E[0])
        return 23
    
    def cbset7h(self, z):
        self._H[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._H[0])
        return 23
    
    def cbset7l(self, z):
        self._L[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._L[0])
        return 23
    
    def cbset7inhl(self, z):
        self.memory.pokeb(z, self.set(0x80, self.memory.peekb(z)))
        return 23
    
    def cbset7a(self, z):
        self._A[0] = self.set(0x80, self.memory.peekb(z))
        self.memory.pokeb(z, self._A[0])
        return 23

    def in_bc(self):
        ans = self.ports.port_in(self._BC[0])
        self._fZ = ans == 0
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        self._f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fN = False
        self._fH = False
        return ans
    
    """
    The algorithm for calculating P/V flag for ADD instruction is: 
    if (((reg_a ^ operand) & 0x80) == 0 /* Same sign */
    && ((reg_a ^ result) & 0x80) != 0) /* Not same sign */
    overflow = 1;
    else
    overflow = 0;
    """
    # Add with carry - alters all flags (CHECKED)
    def adc_a(self, b):
        a = self._A[0]
        c = 1 if self._fC else 0
        ans = (a + b + c) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fC = a > ans
        self._fPV = ((a ^ b) < 0x80) and ((a ^ ans) > 0x7f)
        # self._fH = ((ans ^ a ^ b) & 0x10) != 0
        self._fH = ((a % 16) + (b % 16) + c) > 0x0f
        self._fN = False
        self._A[0] = ans
    
    # Add - alters all flags (CHECKED)
    def add_a(self, b):
        a = self._A[0]
        ans = (a + b) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fC = a > ans
        self._fPV = ((a ^ b) < 0x80) and ((a ^ ans) > 0x7f)
        self._fH = ((a % 16) + (b % 16)) > 0x0f
        self._fN = False
        self._A[0] = ans
    
    # print 'self.add_a(%d): a=%d wans=%d ans=%d' % (b, a, wans, ans)
    
    """
    While for SUB instruction is:
    
    if (((reg_a ^ operand) & 0x80) != 0 /* Not same sign */
    && ((operand ^ result) & 0x80) == 0) /* Same sign */
    overflow = 1;
    else
    overflow = 0; 
    """
    # Subtract with carry - alters all flags (CHECKED)
    def sbc_a(self, b):
        a = self._A[0]
        c = 1 if self._fC else 0
        ans = (a - b - c) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fC = a < ans
        self._fPV = ((a ^ b) > 0x7f) and ((b ^ ans) < 0x80)
        self._fH = ((a % 16) - (b % 16) - c) < 0
        self._fN = True
        self._A[0] = ans
    
    # Subtract - alters all flags (CHECKED)
    def sub_a(self, b):
        a = self._A[0]
        ans = (a - b) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fC = a < ans
        self._fPV = ((a ^ b) > 0x7f) and ((b ^ ans) < 0x80)
        self._fH = ((a % 16) - (b % 16)) < 0
        self._fN = True
        self._A[0] = ans
    
    # Increment - alters all but C flag (CHECKED)
    def inc8(self, ans):
        ans = (ans + 1) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fPV = ans == 0x80
        self._fH = not (ans % 16)
        self._fN = False
        return ans
    
    # Decrement - alters all but C flag (CHECKED)
    def dec8(self, ans):
        h = not (ans % 16)
        ans = (ans - 1) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fPV = ans == 0x7f
        self._fH = h
        self._fN = True
        return ans
    
    # Add with carry - (NOT CHECKED)
    def adc16(self, a, b):
        # print(f'self._fC = {self._fC}, a = 0x{a:4x}, b = 0x{b:4x}')
        c = 1 if self._fC else 0
        ans = (a + b + c) % 65536
        self._fS = ans > 0x7fff
        self._f3 = (ans & F_3_16) != 0 
        _f5 = (ans & F_5_16) != 0
        self._fZ = not ans
        self._fC = a > ans
        self._fPV = ((a ^ b) < 0x8000) and ((a ^ ans) > 0x7fff)
        self._fH = ((a % 0x1000) + (b % 0x1000) + c) > 0x0fff
        self._fH = ((ans ^ a ^ b) & 0x1000) != 0
        self._fN = False
        return ans
    
    # Add - (NOT CHECKED)
    def add16(self, a, b):
        ans = (a + b) % 65536
        self._f3 = (ans & F_3_16) != 0 
        _f5 = (ans & F_5_16) != 0
        self._fC = a > ans
        self._fH = ((a % 0x1000) + (b % 0x1000)) > 0x0fff
        return ans
    
    # Add with carry - (NOT CHECKED)
    def sbc16(self, a, b):
        c = 1 if self._fC else 0
        ans = (a - b - c) % 65536
        self._fS = ans > 0x7fff
        self._f3 = (ans & F_3_16) != 0 
        _f5 = (ans & F_5_16) != 0
        self._fZ = not ans
        self._fC = a < ans
        self._fPV = ((a ^ b) > 0x7fff) and ((b ^ ans) < 0x8000)
        self._fH = ((a % 0x1000) - (b % 0x1000) - c) < 0
        self._fN = True
        return ans
    
    # TODO: check comparisons !
    # Compare - alters all flags (CHECKED)
    def cp_a(self, b):
        a = self._A[0]
        ans = (a - b) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fZ = not ans
        self._fC = a < ans
        self._fPV = ((a ^ b) > 0x7f) and ((b ^ ans) < 0x80)
        self._fH = ((a % 16) - (b % 16)) < 0
        self._fN = True
    
    # Bitwise and - alters all flags (CHECKED)
    def and_a(self, b):
        ans = self._A[0] & b
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fH = True
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fC = False
        self._A[0] = ans
    
    # Bitwise or - alters all flags (CHECKED)
    def or_a(self, b):
        ans = self._A[0] | b
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fH = False
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fC = False
        self._A[0] = ans
    
    # Bitwise exclusive or - alters all flags (CHECKED)
    def xor_a(self, b):
        ans = (self._A[0] ^ b) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fH = False
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fC = False
        self._A[0] = ans
    
    # Test self.bit - alters all but C flag (CHECKED)
    def bit(self, b, r):
        bitset = (r & b) != 0
        self._fS = bitset if b == F_S else False
        self._f3 = (r & F_3) != 0
        _f5 = (r & F_5) != 0
        self._fN = False
        self._fH = True
        self._fZ = not bitset
        self._fPV = self._fZ
    
    # Rotate left - alters all flags (CHECKED)
    def rlc(self, ans):
        c = ans > 0x7f
        ans = ((ans << 1) + (0x01 if c else 0)) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Rotate left through carry - alters all flags (CHECKED)
    def rl(self, ans):
        c = ans > 0x7F
        ans = ((ans << 1) + (1 if self._fC else 0)) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Rotate right - alters all flags (CHECKED)
    def rrc(self, ans):
        c = (ans % 2) != 0
        ans = ((ans >> 1) + (0x80 if c else 0)) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Rotate right through carry - alters all flags (CHECKED)
    def rr(self, ans):
        c = (ans % 2) != 0
        ans = ((ans >> 1) + (0x80 if self._fC else 0)) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Shift Left Arithmetically - alters all flags (CHECKED)
    def sla(self, ans):
        c = ans > 0x7f
        ans = (ans << 1) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Shift Right Arithmetically - alters all flags (CHECKED)
    def sra(self, ans):
        c = (ans % 2) != 0
        b7 = 0x80 if ans > 0x7f else 0 
        ans = ((ans >> 1) + b7) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Shift Right Logically - alters all flags (CHECKED)
    def srl(self, ans):
        c = (ans % 2) != 0
        ans = (ans >> 1) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Shift Left and self.set - alters all flags (CHECKED)
    def sls(self, ans):
        c = ans > 0x7f
        ans = ((ans << 1) + 1) % 256
        self._fS = ans > 0x7f
        self._f3 = (ans & F_3) != 0
        _f5 = (ans & F_5) != 0
        self._fPV = self.parity[ans]
        self._fZ = not ans
        self._fN = False
        self._fH = False
        self._fC = c
        return ans
    
    # Quick Increment : no flags
    @staticmethod
    def inc16(a):
        return (a + 1) % 65536
    
    @staticmethod
    def qinc8(a):
        return (a + 1) % 256
    
    # Quick Decrement : no flags
    @staticmethod
    def dec16(a):
        return (a - 1) % 65536
    
    @staticmethod
    def qdec8(a):
        return (a - 1) % 256
    
    # self.bit toggling
    @staticmethod
    def res(bit, val):
        return val & ~bit
    
    @staticmethod
    def set(bit, val):
        return val | bit
    
    def outb(self, port, value):
        self.ports.port_out(port, value)
