import argparse
import numpy as np
import pygame
import time
import sys

from disassembler import disassemble
from bus import bus

# flake8: noqa


def merge_bytes(high, low):
    """
    Merges two separate bytes to create an address

    e.g.:
        param high is 0x3E
        param low is 0xFF
        resulting address will be 0x3EFF
    """
    return (high << 8) | low


def extract_bytes(adr):
    """
    Splits an address into two words

    e.g.:
        param adr is 0x3EFF
        resulting values are 0x3E (high) and 0xFF (low)
    """
    return (adr >> 8) & 0xff, adr & 0xff


def get_twos_comp(byte):
    return (byte ^ 0xff) + 0x01


def get_msb(byte):
    return byte >> 4


def get_lsb(byte):
    return byte & 0xf


def parity(n):
    """ Sets the parity bit for the Flags construct """
    return (bin(n).count('1') % 2) == 0


class Flags:

    def __init__(self):
        self.z = 0
        self.s = 0
        self.p = 0
        self.cy = 0
        self.ac = 0

    def __int__(self):
        byte = self.cy
        byte |= 0x02
        byte |= self.p << 2
        byte |= self.ac << 4
        byte |= self.z << 6
        byte |= self.s << 7
        return byte


class State:

    def __init__(self, memory):
        self.memory = bytearray(memory) + bytearray(0x8000)  # ROM + RAM
        self.a = 0
        self._cc = Flags()
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = 0
        self.pc = 0
        self.int_enable = 0
        self.cycles = 0

    def calc_flags(self, ans, single=True):
        mask = 0xff if single else 0xffff
        self.cc.z = (ans & mask) == 0
        self.cc.s = (ans & (mask - (mask >> 1))) != 0
        self.cc.cy = ans > mask
        self.cc.p = parity(ans & mask)

    def nop(self):
        self.cycles += 4

    def push(self, reg):
        """
        Push a register pair onto the stack.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw|pc]
        """
        assert reg in 'bc de hl psw pc'.split(), "Register %s is not valid" % reg

        self.memory[self.sp - 1], self.memory[self.sp - 2] = extract_bytes(getattr(self, reg))
        self.sp -= 2
        self.cycles += 11

    def pop(self, reg):
        """
        Pop a value from the stack into a register pair.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw]
        """
        assert reg in 'bc de hl psw'.split(), "Register %s is not valid" % reg

        setattr(self, reg, merge_bytes(self.memory[self.sp + 1], self.memory[self.sp]))
        self.sp += 2
        self.cycles += 10

    def lxi(self, reg, high, low):
        """
        Set a register pair to the specified bytes

        Arguments:
            reg (str): register pair name [bc|de|hl|psw|sp]
            high (int): high byte
            low (int): low byte
        """
        assert reg in 'bc de hl psw sp'.split(), "Register %s is not valid" % reg

        setattr(self, reg, merge_bytes(high, low))
        self.pc += 2
        self.cycles += 10

    def dcr(self, reg):
        """
        Decrease the specified register by 1

        Arguments:
            reg (str): register name [a|b|c|d|e|h|l|m]
        """
        assert reg in 'b c d e h l m a'.split(), "Register %s is not valid" % reg

        if reg == 'm':
            ans = self.memory[self.hl] - 1
        else:
            ans = getattr(self, reg) - 1

        self.calc_flags(ans)

        if reg == 'm':
            self.memory[self.hl] = ans & 0xff
            self.cycles += 10
        else:
            setattr(self, reg, ans & 0xff)
            self.cycles += 5

    def mvi(self, reg, val):
        if reg == 'm':
            self.memory[self.hl] = val
            self.cycles += 10
        else:
            setattr(self, reg, val)
            self.cycles += 7
        self.pc += 1

    def dad(self, reg):
        ans = self.hl + getattr(self, reg)
        self.cc.cy = ans > 0xffff
        self.hl = ans
        self.cycles += 10

    def inx(self, reg):
        ans = getattr(self, reg) + 1
        setattr(self, reg, ans & 0xffff)
        self.cycles += 5

    def dcx(self, reg):
        ans = getattr(self, reg) - 1
        setattr(self, reg, ans & 0xffff)
        self.cycles += 5

    def inr(self, reg):
        if reg == 'm':
            ans = self.memory[self.hl] + 1
        else:
            ans = getattr(self, reg) + 1
        self.calc_flags(ans)
        if reg == 'm':
            self.memory[self.hl] += 1
            self.cycles += 10
        else:
            setattr(self, reg, ans & 0xff)
            self.cycles += 5

    def add(self, reg, carry=False):
        if isinstance(reg, int):
            ans = self.a + reg
            ans += 0 if not carry else self.cc.cy
            self.cycles += 7
        elif reg == 'm':
            ans = self.a + self.memory[self.hl]
            ans += 0 if not carry else self.cc.cy
            self.cycles += 7
        else:
            ans = self.a + getattr(self, reg)
            ans += 0 if not carry else self.cc.cy
            self.cycles += 4
        self.calc_flags(ans)
        self.a = ans & 0xff

    def adc(self, reg):
        self.add(reg, True)

    def sub(self, reg, carry=False):
        if isinstance(reg, int):
            x = reg if not carry else reg + self.cc.cy
            self.cycles += 7
        elif reg == 'm':
            x = self.memory[self.hl] if not carry else self.memory[self.hl] + self.cc.cy
            self.cycles += 7
        else:
            x = getattr(self, reg) if not carry else getattr(self, reg) + self.cc.cy
            self.cycles += 4
        # two's complement
        x = (x ^ 0xff) + 0x01
        self.cc.ac = ((x & 0xf) + (self.a & 0xf)) > 0xf
        ans = self.a + x
        self.cc.cy = ans <= 0xff
        self.cc.s = (ans & 0x80) != 0
        self.cc.z = (ans & 0xff) == 0
        self.cc.p = parity(ans & 0xff)
        self.a = ans & 0xff

    def sbb(self, reg):
        self.sub(reg, True)

    def ana(self, reg):
        if isinstance(reg, int):
            ans = self.a & reg
            self.cycles += 7
        elif reg == 'm':
            ans = self.a & self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a & getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def ora(self, reg):
        if isinstance(reg, int):
            ans = self.a | reg
            self.cycles += 7
        elif reg == 'm':
            ans = self.a | self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a | getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def xra(self, reg):
        if isinstance(reg, int):
            ans = self.a ^ reg
            self.cycles += 7
        elif reg == 'm':
            ans = self.a ^ self.memory[self.hl]
            self.cycles += 7
        else:
            ans = self.a ^ getattr(self, reg)
            self.cycles += 4

        self.calc_flags(ans)
        self.a = ans & 0xff

    def cmp(self, reg):
        if isinstance(reg, int):
            tc_val = get_twos_comp(reg)
            self.cycles += 7
        elif reg == 'm':
            tc_val = get_twos_comp(self.memory[self.hl])
            self.cycles += 7
        else:
            tc_val = get_twos_comp(self.memory[self.hl])
            self.cycles += 4
        self.cc.ac = (get_lsb(self.a) + get_lsb(tc_val)) > 0xf
        ans = self.a + tc_val
        self.cc.cy = ans <= 0xff
        self.cc.z = (ans & 0xff) == 0x00
        self.cc.s = (ans & 0x80) != 0
        self.cc.p = parity(ans)

    def stax(self, reg):
        self.memory[getattr(self, reg)] = self.a
        self.cycles += 7

    def rst(self, i):
        self.int_enable = 0
        self.push('pc')
        self.pc = 8 * i
        self.cycles += 11

    def jmp(self, adr, cc=None, opposite=False):
        if cc:
            cc = getattr(self.cc, cc)
            # generalization for FLAG/NOTFLAG
            if bool(cc) != opposite:
                self.pc = adr
            else:
                self.pc += 3
        else:
            self.pc = adr
        self.cycles += 10

    def ret(self, cc=None, opposite=False):
        if cc:
            cc = getattr(self.cc, cc)
            if bool(cc) != opposite:
                self.pc = merge_bytes(self.memory[self.sp + 1], self.memory[self.sp])
                self.sp += 2
                self.cycles += 11
            else:
                self.cycles += 5
                self.pc += 1
        else:
            self.pc = merge_bytes(self.memory[self.sp + 1], self.memory[self.sp])
            self.sp += 2
            self.cycles += 10

    def call(self, adr, cc=None, opposite=False):
        if cc:
            cc = getattr(self.cc, cc)
            if bool(cc) != opposite:
                self.cycles += 17
                ret = self.pc + 3
                hi, lo = extract_bytes(ret)
                self.memory[self.sp - 1] = hi
                self.memory[self.sp - 2] = lo
                self.sp -= 2
                self.pc = adr
            else:
                self.cycles += 11
                self.pc += 3
        else:
            self.cycles += 17
            ret = self.pc + 3
            hi, lo = extract_bytes(ret)
            self.memory[self.sp - 1] = hi
            self.memory[self.sp - 2] = lo
            self.sp -= 2
            self.pc = adr

    @property
    def cc(self):
        return self._cc

    @cc.setter
    def cc(self, val):
        self._cc.cy = (val & 0x01) != 0
        self._cc.p = (val & 0x04) != 0
        self._cc.ac = (val & 0x10) != 0
        self._cc.z = (val & 0x40) != 0
        self._cc.s = (val & 0x80) != 0

    @property
    def psw(self):
        return merge_bytes(self.a, int(self.cc))

    @psw.setter
    def psw(self, val):
        self.a, self.cc = extract_bytes(val)

    @property
    def bc(self):
        return merge_bytes(self.b, self.c)

    @bc.setter
    def bc(self, val):
        self.b, self.c = extract_bytes(val)

    @property
    def de(self):
        return merge_bytes(self.d, self.e)

    @de.setter
    def de(self, val):
        self.d, self.e = extract_bytes(val)

    @property
    def hl(self):
        return merge_bytes(self.h, self.l)

    @hl.setter
    def hl(self, val):
        self.h, self.l = extract_bytes(val)

    @property
    def bitmap(self):

        def bitarray(byte):
            return [(byte >> i) & 1 for i in range(7, -1, -1)]

        def bit2rgb(bit):
            if bit:
                return [255, 255, 255]
            return [0, 0, 0]

        video_ram = self.memory[0x2400:]

        bytemap = []
        for i in range(224):
            start = i * 32
            # Inverse bcz little-endianness?
            bytemap.append(video_ram[start:start + 32][::-1])

        bitmap = []
        for row in bytemap:
            line = []
            for byte in row:
                line += bitarray(byte)
            bitmap.append(line)

        for i, row in enumerate(bitmap):
            for j, col in enumerate(row):
                bitmap[i][j] = bit2rgb(col)

        return np.array(bitmap)


def emulate(state, debug=0, opcode=None):

    # XXX: You *really* don't wanna reach the end of the memory
    if not opcode:
        opcode = state.memory[state.pc]
        arg1 = None if (state.pc + 1) >= len(state.memory) else state.memory[state.pc + 1]
        arg2 = None if (state.pc + 2) >= len(state.memory) else state.memory[state.pc + 2]
        if debug:
            disassemble(state.memory, state.pc)
        if debug > 1:
            print("\tC=%d, P=%d, S=%d, Z=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z))
            print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
                state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
            ))

    if opcode == 0x00:
        # NOP
        state.nop()
    elif opcode == 0x01:
        # LXI B, D16
        state.lxi('bc', arg2, arg1)
    elif opcode == 0x02:
        # STAX B
        state.stax('bc')
    elif opcode == 0x03:
        # INX B
        state.inx('bc')
    elif opcode == 0x04:
        # INR B
        state.inr('b')
    elif opcode == 0x05:
        # DCR B
        state.dcr('b')
    elif opcode == 0x06:
        # MVI B, D8
        state.mvi('b', arg1)
    elif opcode == 0x07:
        # RLC
        h = state.a & 0x80
        state.cc.cy = h
        state.a = (state.a << 1) | h
        state.cycles += 4
    elif opcode == 0x08:
        # NOP*
        state.nop()
    elif opcode == 0x09:
        # DAD B
        state.dad('bc')
    elif opcode == 0x0a:
        # LDAX B
        state.a = state.memory[state.bc]
        state.cycles += 7
    elif opcode == 0x0b:
        # DCX B
        state.dcx('bc')
    elif opcode == 0x0c:
        # INR C
        state.inr('c')
    elif opcode == 0x0d:
        # DCR C
        state.dcr('c')
    elif opcode == 0x0e:
        # MVI C, D8
        state.mvi('c', arg1)
    elif opcode == 0x0f:
        # RRC
        x = state.a
        state.a = ((x & 1) << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
        state.cycles += 4
    elif opcode == 0x10:
        # NOP*
        state.nop()
    elif opcode == 0x11:
        # LXI D, D16
        state.lxi('de', arg2, arg1)
    elif opcode == 0x12:
        # STAX D
        state.stax('de')
    elif opcode == 0x13:
        # INX D
        state.inx('de')
    elif opcode == 0x14:
        # INR D
        state.inr('d')
    elif opcode == 0x15:
        # DCR D
        state.dcr('d')
    elif opcode == 0x16:
        # MVI D, D8
        state.mvi('d', arg1)
    elif opcode == 0x17:
        # RAL
        x = state.a
        state.a = (x << 1) | state.cc.cy
        state.cc.cy = (x & 0x80) == 1
        state.cycles += 4
    elif opcode == 0x18:
        # NOP*
        state.nop()
    elif opcode == 0x19:
        # DAD D
        state.dad('de')
    elif opcode == 0x1a:
        # LDAX D
        state.a = state.memory[state.de]
        state.cycles += 7
    elif opcode == 0x1b:
        # DCX D
        state.dcx('de')
    elif opcode == 0x1c:
        # INR E
        state.inr('e')
    elif opcode == 0x1d:
        # DCR E
        state.dcr('e')
    elif opcode == 0x1e:
        # MVI E, D8
        state.mvi('e', arg1)
    elif opcode == 0x1f:
        # RAR
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
        state.cycles += 4
    elif opcode == 0x20:
        # NOP*
        state.nop()
    elif opcode == 0x21:
        # LXI H, D16
        state.lxi('hl', arg2, arg1)
    elif opcode == 0x22:
        # SHLD, adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.l
        state.memory[adr + 1] = state.h
        state.cycles += 16
        state.pc += 2
    elif opcode == 0x23:
        # INX H
        state.inx('hl')
    elif opcode == 0x24:
        # INR H
        state.inr('h')
    elif opcode == 0x25:
        # DCR H
        state.dcr('h')
    elif opcode == 0x26:
        # MVI H, D8
        state.mvi('h', arg1)
    elif opcode == 0x27:
        # DAA
        lsb = state.a & 0x0f
        if lsb > 9 or state.cc.ac:
            state.a = (state.a + 0x06) & 0xff
            state.cc.ac = (lsb + 0x06) > 0x0f
        msb = state.a >> 4
        if msb > 9 or state.cc.cy:
            state.a = (state.a + 0x60) & 0xff
            state.cc.cy = (msb + 0x06) > 0x0f
        else:
            state.cc.cy = 0
        state.cc.p = parity(state.a)
        state.cc.z = state.a == 0
        state.cc.s = (state.a & 0x80) != 0
        state.cycles += 4
    elif opcode == 0x28:
        # NOP*
        state.nop()
    elif opcode == 0x29:
        # DAD H
        state.dad('hl')
    elif opcode == 0x2a:
        # LXI H, D16
        state.lxi('hl', arg2, arg1)
    elif opcode == 0x2b:
        # DCX H
        state.dcx('hl')
    elif opcode == 0x2c:
        # INR L
        state.inr('l')
    elif opcode == 0x2d:
        # DCR L
        state.dcr('l')
    elif opcode == 0x2e:
        # MVI L, D8
        state.mvi('l', arg1)
    elif opcode == 0x2f:
        # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a ^= 0xff
        state.cycles += 4
    elif opcode == 0x30:
        # NOP*
        state.nop()
    elif opcode == 0x31:
        # LXI SP, D16
        state.lxi('sp', arg2, arg1)
    elif opcode == 0x32:
        # STA adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.a
        state.pc += 2
        state.cycles += 13
    elif opcode == 0x33:
        # INX SP
        state.inx('sp')
    elif opcode == 0x34:
        # INR M
        state.inr('m')
    elif opcode == 0x35:
        # DCR M
        state.dcr('m')
    elif opcode == 0x36:
        # MVI M, D8
        state.mvi('m', arg1)
    elif opcode == 0x37:
        # STC
        state.cc.cy = 1
        state.cycles += 4
    elif opcode == 0x38:
        # NOP*
        state.nop()
    elif opcode == 0x39:
        # DAD SP
        state.dad('sp')
    elif opcode == 0x3a:
        # LDA adr
        adr = merge_bytes(arg2, arg1)
        state.a = state.memory[adr]
        state.pc += 2
        state.cycles += 13
    elif opcode == 0x3b:
        # DCX SP
        state.dcx('sp')
    elif opcode == 0x3c:
        # INR A
        state.inr('a')
    elif opcode == 0x3d:
        # DCR A
        state.dcr('a')
    elif opcode == 0x3e:
        # MVI A, D8
        state.mvi('a', arg1)
    elif opcode == 0x3f:
        # CMC
        state.cc.cy ^= 0x01
    elif opcode == 0x40:
        # MOV B, B
        state.cycles += 5
    elif opcode == 0x41:
        # MOV B, C
        state.b = state.c
        state.cycles += 5
    elif opcode == 0x42:
        # MOV B, D
        state.b = state.d
        state.cycles += 5
    elif opcode == 0x43:
        # MOV, B, E
        state.b = state.e
        state.cycles += 5
    elif opcode == 0x44:
        # MOV B, H
        state.b = state.h
        state.cycles += 5
    elif opcode == 0x45:
        # MOV B, L
        state.b = state.l
        state.cycles += 5
    elif opcode == 0x46:
        # MOV B, M
        state.b = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x47:
        # MOV B, A
        state.b = state.a
        state.cycles += 5
    elif opcode == 0x48:
        # MOV C, B
        state.c = state.b
        state.cycles += 5
    elif opcode == 0x49:
        # MOV C, C
        state.cycles += 5
    elif opcode == 0x4a:
        # MOV C, D
        state.c = state.d
        state.cycles += 5
    elif opcode == 0x4b:
        # MOV C, E
        state.c = state.e
        state.cycles += 5
    elif opcode == 0x4c:
        # MOV C, H
        state.c = state.h
        state.cycles += 5
    elif opcode == 0x4d:
        # MOV C, L
        state.c = state.l
        state.cycles += 5
    elif opcode == 0x4e:
        # MOV C, M
        state.c = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x4f:
        # MOV C, A
        state.c = state.a
        state.cycles += 5
    elif opcode == 0x50:
        # MOV D, B
        state.d = state.b
        state.cycles += 5
    elif opcode == 0x51:
        # MOV D, C
        state.d = state.c
        state.cycles += 5
    elif opcode == 0x52:
        # MOV D, D
        state.cycles += 5
    elif opcode == 0x53:
        # MOV D, E
        state.d = state.e
        state.cycles += 5
    elif opcode == 0x54:
        # MOV D, H
        state.d = state.h
        state.cycles += 5
    elif opcode == 0x55:
        # MOV D, L
        state.d = state.l
        state.cycles += 5
    elif opcode == 0x56:
        # MOV D, M
        state.d = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x57:
        # MOV D, A
        state.d = state.a
        state.cycles += 5
    elif opcode == 0x58:
        # MOV E, B
        state.e = state.b
        state.cycles += 5
    elif opcode == 0x59:
        # MOV E, C
        state.e = state.c
        state.cycles += 5
    elif opcode == 0x5a:
        # MOV E, D
        state.e = state.d
        state.cycles += 5
    elif opcode == 0x5b:
        # MOV E, E
        state.cycles += 5
    elif opcode == 0x5c:
        # MOV E, H
        state.e = state.h
        state.cycles += 5
    elif opcode == 0x5d:
        # MOV E, L
        state.e = state.l
        state.cycles += 5
    elif opcode == 0x5e:
        # MOV E, M
        state.e = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x5f:
        # MOV E, A
        state.e = state.a
        state.cycles += 5
    elif opcode == 0x60:
        # MOV H, B
        state.h = state.b
        state.cycles += 5
    elif opcode == 0x61:
        # MOV H, C
        state.h = state.c
        state.cycles += 5
    elif opcode == 0x62:
        # MOV H, D
        state.h = state.d
        state.cycles += 5
    elif opcode == 0x63:
        # MOV H, E
        state.h = state.e
        state.cycles += 5
    elif opcode == 0x64:
        # MOV H, H
        state.cycles += 5
    elif opcode == 0x65:
        # MOV H, L
        state.h = state.l
        state.cycles += 5
    elif opcode == 0x66:
        # MOV H, M
        state.h = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x67:
        # MOV H, A
        state.h = state.a
        state.cycles += 5
    elif opcode == 0x68:
        # MOV L, B
        state.l = state.b
        state.cycles += 5
    elif opcode == 0x69:
        # MOV L, C
        state.l = state.c
        state.cycles += 5
    elif opcode == 0x6a:
        # MOV L, D
        state.l = state.d
        state.cycles += 5
    elif opcode == 0x6b:
        # MOV L, E
        state.l = state.e
        state.cycles += 5
    elif opcode == 0x6c:
        # MOV L, H
        state.l = state.h
        state.cycles += 5
    elif opcode == 0x6d:
        # MOV L, L
        state.cycles += 5
    elif opcode == 0x6e:
        # MOV L, M
        state.l = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x6f:
        # MOV L, A
        state.l = state.a
        state.cycles += 5
    elif opcode == 0x70:
        # MOV M, B
        state.memory[state.hl] = state.b
        state.cycles += 7
    elif opcode == 0x71:
        # MOV M, C
        state.memory[state.hl] = state.c
        state.cycles += 7
    elif opcode == 0x72:
        # MOV M, D
        state.memory[state.hl] = state.d
        state.cycles += 7
    elif opcode == 0x73:
        # MOV M, E
        state.memory[state.hl] = state.e
        state.cycles += 7
    elif opcode == 0x74:
        # MOV M, H
        state.memory[state.hl] = state.h
        state.cycles += 7
    elif opcode == 0x75:
        # MOV M, L
        state.memory[state.hl] = state.l
        state.cycles += 7
    elif opcode == 0x76:
        # HLT
        state.cycles = 7
        sys.exit(0)
    elif opcode == 0x77:
        # MOV M, A
        state.memory[state.hl] = state.a
        state.cycles += 7
    elif opcode == 0x78:
        # MOV A, B
        state.a = state.b
        state.cycles += 5
    elif opcode == 0x79:
        # MOv A, C
        state.a = state.c
        state.cycles += 5
    elif opcode == 0x7a:
        # MOV A, D
        state.a = state.d
        state.cycles += 5
    elif opcode == 0x7b:
        # MOV A, E
        state.a = state.e
        state.cycles += 5
    elif opcode == 0x7c:
        # MOV A, H
        state.a = state.h
        state.cycles += 5
    elif opcode == 0x7d:
        # MOV A, L
        state.a = state.l
        state.cycles += 5
    elif opcode == 0x7e:
        # MOV A, M
        state.a = state.memory[state.hl]
        state.cycles += 7
    elif opcode == 0x7f:
        # MOV A, A
        state.cycles += 5
    elif opcode == 0x80:
        # ADD B
        state.add('b')
    elif opcode == 0x81:
        # ADD C
        state.add('c')
    elif opcode == 0x82:
        # ADD D
        state.add('d')
    elif opcode == 0x83:
        # ADD E
        state.add('e')
    elif opcode == 0x84:
        # ADD H
        state.add('h')
    elif opcode == 0x85:
        # ADD L
        state.add('l')
    elif opcode == 0x86:
        # ADD M
        state.add('m')
    elif opcode == 0x87:
        # ADD A
        state.add('a')
    elif opcode == 0x88:
        # ADC B
        state.adc('b')
    elif opcode == 0x89:
        # ADC C
        state.adc('c')
    elif opcode == 0x8a:
        # ADC D
        state.adc('d')
    elif opcode == 0x8b:
        # ADC E
        state.adc('e')
    elif opcode == 0x8c:
        # ADC H
        state.adc('h')
    elif opcode == 0x8d:
        # ADC L
        state.adc('l')
    elif opcode == 0x8e:
        # ADC M
        state.adc('m')
    elif opcode == 0x8f:
        # ADC A
        state.adc('a')
    elif opcode == 0x90:
        # SUB B
        state.sub('b')
    elif opcode == 0x91:
        # SUB C
        state.sub('c')
    elif opcode == 0x92:
        # SUB D
        state.sub('d')
    elif opcode == 0x93:
        # SUB E
        state.sub('e')
    elif opcode == 0x94:
        # SUB H
        state.sub('h')
    elif opcode == 0x95:
        # SUB L
        state.sub('l')
    elif opcode == 0x96:
        # SUB M
        state.sub('m')
    elif opcode == 0x97:
        # SUB A
        state.sub('a')
    elif opcode == 0x98:
        # SBB B
        state.sbb('b')
    elif opcode == 0x99:
        # SBB C
        state.sbb('c')
    elif opcode == 0x9a:
        # SBB D
        state.sbb('d')
    elif opcode == 0x9b:
        # SBB E
        state.sbb('e')
    elif opcode == 0x9c:
        # SBB H
        state.sbb('h')
    elif opcode == 0x9d:
        # SBB L
        state.sbb('l')
    elif opcode == 0x9e:
        # SBB M
        state.sbb('m')
    elif opcode == 0x9f:
        # SBB A
        state.sbb('a')
    elif opcode == 0xa0:
        # ANA B
        state.ana('b')
    elif opcode == 0xa1:
        # ANA C
        state.ana('c')
    elif opcode == 0xa2:
        # ANA D
        state.ana('d')
    elif opcode == 0xa3:
        # ANA E
        state.ana('e')
    elif opcode == 0xa4:
        # ANA H
        state.ana('h')
    elif opcode == 0xa5:
        # ANA L
        state.ana('l')
    elif opcode == 0xa6:
        # ANA M
        state.ana('m')
    elif opcode == 0xa7:
        # ANA A
        state.ana('a')
    elif opcode == 0xa8:
        # XRA B
        state.xra('b')
    elif opcode == 0xa9:
        # XRA C
        state.xra('c')
    elif opcode == 0xaa:
        # XRA D
        state.xra('d')
    elif opcode == 0xab:
        # XRA E
        state.xra('e')
    elif opcode == 0xac:
        # XRA H
        state.xra('h')
    elif opcode == 0xad:
        # XRA L
        state.xra('l')
    elif opcode == 0xae:
        # XRA M
        state.xra('m')
    elif opcode == 0xaf:
        # XRA A
        state.xra('a')
    elif opcode == 0xb0:
        # ORA B
        state.ora('b')
    elif opcode == 0xb1:
        # ORA C
        state.ora('c')
    elif opcode == 0xb2:
        # ORA D
        state.ora('d')
    elif opcode == 0xb3:
        # ORA E
        state.ora('e')
    elif opcode == 0xb4:
        # ORA H
        state.ora('h')
    elif opcode == 0xb5:
        # ORA L
        state.ora('l')
    elif opcode == 0xb6:
        # ORA M
        state.ora('m')
    elif opcode == 0xb7:
        # ORA A
        state.ora('a')
    elif opcode == 0xb8:
        # CMP B
        state.cmp('b')
    elif opcode == 0xb9:
        # CMP C
        state.cmp('c')
    elif opcode == 0xba:
        # CMP D
        state.cmp('d')
    elif opcode == 0xbb:
        # CMP E
        state.cmp('e')
    elif opcode == 0xbc:
        # CMP H
        state.cmp('h')
    elif opcode == 0xbd:
        # CMP L
        state.cmp('l')
    elif opcode == 0xbe:
        # CMP M
        state.cmp('m')
    elif opcode == 0xbf:
        # CMP A
        state.cmp('a')
    elif opcode == 0xc0:
        # RNZ
        return state.ret('z', True)
    elif opcode == 0xc1:
        # POP B
        state.pop('bc')
    elif opcode == 0xc2:
        # JNZ adr
        return state.jmp(merge_bytes(arg2, arg1), 'z', True)
    elif opcode == 0xc3:
        # JMP adr
        return state.jmp(merge_bytes(arg2, arg1))
    elif opcode == 0xc4:
        # CNZ adr
        return state.call(merge_bytes(arg2, arg1), 'z', True)
    elif opcode == 0xc5:
        # PUSH B
        state.push('bc')
    elif opcode == 0xc6:
        # ADI byte
        state.add(arg1)
        state.pc += 1
    elif opcode == 0xc7:
        # RST 0
        return state.rst(0)
    elif opcode == 0xc8:
        # RZ
        return state.ret('z')
    elif opcode == 0xc9:
        # RET
        return state.ret()
    elif opcode == 0xca:
        # JZ adr
        return state.jmp(merge_bytes(arg2, arg1), 'z')
    elif opcode == 0xcc:
        # CZ adr
        return state.call(merge_bytes(arg2, arg1), 'z')
    elif opcode == 0xcd:
        # CALL adr
        return state.call(merge_bytes(arg2, arg1))
    elif opcode == 0xce:
        # ACI D8
        state.adc(arg1)
        state.pc += 1
    elif opcode == 0xcf:
        # RST 1
        return state.rst(1)
    elif opcode == 0xd0:
        # RNC
        return state.ret('cy', True)
    elif opcode == 0xd1:
        # POP D
        state.pop('de')
    elif opcode == 0xd2:
        # JNC adr
        return state.jmp(merge_bytes(arg2, arg1), 'cy', True)
    elif opcode == 0xd3:
        # OUT byte
        bus.write(arg1, state.a)
        state.pc += 1
        state.cycles += 10
    elif opcode == 0xd4:
        # CNC adr
        return state.call(merge_bytes(arg2, arg1), 'cy', True)
    elif opcode == 0xd5:
        # PUSH D
        state.push('de')
    elif opcode == 0xd6:
        # SUI D8
        state.sub(arg1)
        state.pc += 1
    elif opcode == 0xd7:
        # RST 2
        return state.rst(2)
    elif opcode == 0xd8:
        # RC
        return state.ret('cy')
    elif opcode == 0xd9:
        # RET*
        return state.ret()
    elif opcode == 0xda:
        # JC adr
        return state.jmp(merge_bytes(arg2, arg1), 'cy')
    elif opcode == 0xdb:
        # IN D8
        state.a = bus.read(arg1)
        state.pc += 1
        state.cycles += 10
    elif opcode == 0xdc:
        # CC adr
        return state.call(merge_bytes(arg2, arg1), 'cy')
    elif opcode == 0xdd:
        # CALL* adr
        return state.call(merge_bytes(arg2, arg1))
    elif opcode == 0xde:
        # SBI D8
        state.sbb(arg1)
        state.pc += 1
    elif opcode == 0xdf:
        # RST 3
        return state.rst(3)
    elif opcode == 0xe0:
        # RPO
        return state.ret('p', True)
    elif opcode == 0xe1:
        # POP H
        state.pop('hl')
    elif opcode == 0xe2:
        # JPO adr
        return state.jmp(merge_bytes(arg2, arg1), 'p', True)
    elif opcode == 0xe3:
        # XTHL
        state.l, state.memory[state.sp] = state.memory[state.sp], state.l
        state.h, state.memory[state.sp + 1] = state.memory[state.sp + 1], state.h
        state.cycles += 18
    elif opcode == 0xe4:
        # CPO adr
        return state.call(merge_bytes(arg2, arg1), 'p', True)
    elif opcode == 0xe5:
        # PUSH H
        state.push('hl')
    elif opcode == 0xe6:
        # ANI byte
        state.ana(arg1)
        state.pc += 1
    elif opcode == 0xe7:
        return state.rst(4)
    elif opcode == 0xe8:
        # RPE
        return state.ret('p')
    elif opcode == 0xe9:
        # PCHL
        state.pc = state.hl
        state.cycles += 5
    elif opcode == 0xea:
        # JPE adr
        return state.jmp(merge_bytes(arg2, arg1), 'p')
    elif opcode == 0xeb:
        # XCHG
        state.hl, state.de = state.de, state.hl
        state.cycles += 5
    elif opcode == 0xec:
        # CPE adr
        return state.call(merge_bytes(arg2, arg1), 'p')
    elif opcode == 0xed:
        # CALL* adr
        return state.call(merge_bytes(arg2, arg1))
    elif opcode == 0xee:
        # XRI D8
        state.xra(arg1)
        state.pc += 1
    elif opcode == 0xef:
        # RST 5
        return state.rst(5)
    elif opcode == 0xf0:
        # RP
        return state.ret('s', True)
    elif opcode == 0xf1:
        # POP PSW
        state.pop('psw')
    elif opcode == 0xf2:
        # JP adr
        return state.jmp(merge_bytes(arg2, arg1), 's', True)
    elif opcode == 0xf3:
        # DI
        state.int_enable = 0
        state.cycles += 4
    elif opcode == 0xf4:
        # CP adr
        return state.call(merge_bytes(arg2, arg1), 's', True)
    elif opcode == 0xf5:
        # PUSH PSW
        state.push('psw')
    elif opcode == 0xf6:
        # ORI D8
        state.ora(arg1)
        state.pc += 1
    elif opcode == 0xf7:
        # RST 6
        return state.rst(6)
    elif opcode == 0xf8:
        # RM
        return state.ret('s')
    elif opcode == 0xf9:
        # SPHL
        state.sp = state.hl
    elif opcode == 0xfa:
        # JM adr
        return state.jmp(merge_bytes(arg2, arg1), 's')
    elif opcode == 0xfb:
        # EI
        state.int_enable = 1
        state.cycles += 4
    elif opcode == 0xfc:
        # CM adr
        return state.call(merge_bytes(arg2, arg1), 's')
    elif opcode == 0xfd:
        # CALL* adr
        return state.call(merge_bytes(arg2, arg1))
    elif opcode == 0xfe:
        # CPI, D8
        state.cmp(arg1)
        state.pc += 1
    elif opcode == 0xff:
        # RST 7
        return state.rst(7)
    else:
        raise NotImplementedError("opcode %02x is not implemented" % opcode)

    state.pc += 1


def parse():
    parser = argparse.ArgumentParser(
        description="Emulate programs for the Intel 8080 processor"
    )
    parser.add_argument('-d', '--debug', action='count', default=0,
                        help="Display debug output, can be specified up to 3 times")
    parser.add_argument('bin', nargs=1, help="Program to execute")
    parser.add_argument('-H', '--headless', action='store_true', default=False,
                        help="Launch game without rendering it, for debugging purposes")
    return parser.parse_args()


def main():
    args = parse()

    with open(args.bin[0], 'rb') as f:
        state = State(f.read())

    pygame.display.init()
    pygame.time.Clock().tick(60)
    screen = pygame.display.set_mode((224, 256))

    count = 1
    while 1:
        if state.int_enable:
            if bus.loop(state.cycles):
                # Screen refresh
                if not args.headless:
                    # TODO: optimize by keeping track of previous bitmap and comparing
                    screen.fill((0, 0, 0))
                    screen.convert()
                    pygame.surfarray.blit_array(screen, state.bitmap)
                    pygame.display.flip()
                state.cycles = 0
                emulate(state, args.debug, bus.interrupts.popleft())
                continue

        emulate(state, args.debug)

        if args.debug >= 3:
            print("Instruction count: %d" % count)
            count += 1

        if args.debug >= 4:
            print("Current cycles: %d" % state.cycles)


if __name__ == '__main__':
    main()
