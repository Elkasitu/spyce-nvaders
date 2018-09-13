import argparse

from disassembler import disassemble


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


def parity(n):
    """ Sets the parity bit for the Flags construct """
    return n % 2 == 0


class Flags:

    def __init__(self):
        self.z = 0
        self.s = 0
        self.p = 0
        self.cy = 0
        self.ac = 0

    def __int__(self):
        return self.z | (self.s << 1) | (self.p << 2) | (self.cy << 3) | (self.ac << 4)


class State:

    def __init__(self, memory):
        self.memory = bytearray(memory) + bytearray(0x2000)  # ROM + RAM
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

    def calc_flags(self, ans, single=True):
        mask = 0xff if single else 0xffff
        self.cc.z = (ans & mask) == 0
        self.cc.s = (ans & (mask - (mask >> 1))) != 0
        self.cc.cy = ans > mask
        self.cc.p = parity(ans & mask)

    def push(self, reg):
        """
        Push a register pair onto the stack.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw]
        """
        assert reg in 'bc de hl psw'.split(), "Register %s is not valid" % reg

        self.memory[self.sp - 1], self.memory[self.sp - 2] = extract_bytes(getattr(self, reg))
        self.sp -= 2

    def pop(self, reg):
        """
        Pop a value from the stack into a register pair.

        Arguments:
            reg (str): register pair name [bc|de|hl|psw]
        """
        assert reg in 'bc de hl psw'.split(), "Register %s is not valid" % reg

        setattr(self, reg, merge_bytes(self.memory[self.sp + 1], self.memory[self.sp]))
        self.sp += 2

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
        else:
            setattr(self, reg, ans & 0xff)

    def mvi(self, reg, val):
        if reg == 'm':
            self.memory[self.hl] = val
        else:
            setattr(self, reg, val)
        self.pc += 1

    def dad(self, reg):
        ans = self.hl + getattr(self, reg)
        self.cc.cy = ans > 0xffff
        self.hl = ans

    def inx(self, reg):
        ans = getattr(self, reg) + 1
        self.calc_flags(ans, False)
        setattr(self, reg, ans & 0xffff)

    def add(self, reg):
        if reg == 'm':
            ans = self.a + self.memory[self.hl]
        else:
            ans = self.a + getattr(self, reg)
        self.calc_flags(ans)
        self.a = ans & 0xff

    def ana(self, reg):
        ans = self.a & getattr(self, reg)
        self.calc_flags(ans)
        self.a = ans & 0xff

    def ora(self, reg):
        ans = self.a | getattr(self, reg)
        self.calc_flags(ans)
        self.a = ans & 0xff

    def xra(self, reg):
        ans = self.a ^ getattr(self, reg)
        self.calc_flags(ans)
        self.a = ans & 0xff

    def stax(self, reg):
        self.memory[getattr(self, reg)] = self.a

    @property
    def cc(self):
        return self._cc

    @cc.setter
    def cc(self, val):
        self._cc.z = (0x01 == (val & 0x01))
        self._cc.s = (0x02 == (val & 0x02))
        self._cc.p = (0x04 == (val & 0x04))
        self._cc.cy = (0x08 == (val & 0x08))
        self._cc.ac = (0x10 == (val & 0x10))

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


devices = {}


def emulate(state, debug=0):

    # XXX: You *really* don't wanna reach the end of the memory
    opcode, arg1, arg2 = state.memory[state.pc:state.pc + 3]

    if debug:
        disassemble(state.memory, state.pc)
    if debug > 1:
        print("\tC=%d, P=%d, S=%d, Z=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z))
        print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
            state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
        ))

    if opcode == 0x00:
        # NOP
        pass
    elif opcode == 0x01:
        # LXI B, D16
        state.lxi('bc', arg2, arg1)
    elif opcode == 0x02:
        # STAX B
        state.stax('bc')
    elif opcode == 0x05:
        # DCR B
        state.dcr('b')
    elif opcode == 0x06:
        # MVI B, D8
        state.mvi('b', arg1)
    elif opcode == 0x09:
        # DAD B
        state.dad('bc')
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
    elif opcode == 0x11:
        # LXI D, D16
        state.lxi('de', arg2, arg1)
    elif opcode == 0x13:
        # INX D
        state.inx('de')
    elif opcode == 0x19:
        # DAD D
        state.dad('de')
    elif opcode == 0x1a:
        # LDAX D
        state.a = state.memory[state.de]
    elif opcode == 0x1f:
        # RAR
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode == 0x21:
        # LXI H, D16
        state.lxi('hl', arg2, arg1)
    elif opcode == 0x23:
        # INX H
        state.inx('hl')
    elif opcode == 0x26:
        # MVI H, D8
        state.mvi('h', arg1)
    elif opcode == 0x29:
        # DAD H
        state.dad('hl')
    elif opcode == 0x2f:
        # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a ^= 0xff
    elif opcode == 0x31:
        # LXI SP, D16
        state.lxi('sp', arg2, arg1)
    elif opcode == 0x32:
        # STA adr
        adr = merge_bytes(arg2, arg1)
        state.memory[adr] = state.a
        state.pc += 2
    elif opcode == 0x36:
        # MVI M, D8
        state.mvi('m', arg1)
    elif opcode == 0x3a:
        # LDA adr
        adr = merge_bytes(arg2, arg1)
        state.a = state.memory[adr]
        state.pc += 2
    elif opcode == 0x3e:
        # MVI A, D8
        state.mvi('a', arg1)
    elif opcode == 0x41:
        # MOV B, C
        state.b = state.c
    elif opcode == 0x42:
        # MOV B, D
        state.b = state.d
    elif opcode == 0x43:
        # MOV, B, E
        state.b = state.e
    elif opcode == 0x56:
        # MOV D, M
        state.d = state.memory[state.hl]
    elif opcode == 0x5e:
        # MOV E, M
        state.e = state.memory[state.hl]
    elif opcode == 0x66:
        # MOV H, M
        state.h = state.memory[state.hl]
    elif opcode == 0x6f:
        # MOV L, A
        state.l = state.a
    elif opcode == 0x77:
        # MOV M, A
        state.memory[state.hl] = state.a
    elif opcode == 0x7a:
        # MOV A, D
        state.a = state.d
    elif opcode == 0x7b:
        # MOV A, E
        state.a = state.e
    elif opcode == 0x7c:
        # MOV A, H
        state.a = state.h
    elif opcode == 0x7e:
        # MOV A, M
        state.a = state.memory[state.hl]
    elif opcode == 0x80:
        # ADD B
        state.add('b')
    elif opcode == 0x81:
        # ADD C
        state.add('c')
    elif opcode == 0x86:
        # ADD M
        state.add('m')
    elif opcode == 0xa7:
        # ANA A
        state.ana('a')
    elif opcode == 0xaf:
        # XRA A
        state.xra('a')
    elif opcode == 0xb3:
        # ORA E
        state.ora('e')
    elif opcode == 0xc1:
        # POP B
        state.pop('bc')
    elif opcode == 0xc2:
        # JNZ adr
        if state.cc.z == 0:
            state.pc = merge_bytes(arg2, arg1)
            return
        else:
            state.pc += 2
    elif opcode == 0xc3:
        # JMP adr
        state.pc = merge_bytes(arg2, arg1)
        return
    elif opcode == 0xc5:
        # PUSH B
        state.push('bc')
    elif opcode == 0xc6:
        # ADI byte
        ans = state.a + arg1
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
        state.pc += 1
    elif opcode == 0xc9:
        # RET
        # set pc to ret adr
        state.pc = merge_bytes(state.memory[state.sp + 1], state.memory[state.sp])
        # restore stack pointer
        state.sp += 2
    elif opcode == 0xca:
        # JZ
        if state.cc.z:
            state.pc = merge_bytes(arg2, arg1)
    elif opcode == 0xcd:
        # CALL adr
        # put the return address on the stack first
        ret = state.pc + 2
        hi, lo = extract_bytes(ret)
        state.memory[state.sp - 1] = hi
        state.memory[state.sp - 2] = lo
        state.sp -= 2
        # then go to adr
        state.pc = merge_bytes(arg2, arg1)
        return
    elif opcode == 0xd1:
        # POP D
        state.pop('de')
    elif opcode == 0xd3:
        # OUT byte
        # palceholder while I discover what the device is supposed to do
        devices[arg1] = state.a
        state.pc += 1
    elif opcode == 0xd5:
        # PUSH D
        state.push('de')
    elif opcode == 0xe1:
        # POP H
        state.pop('hl')
    elif opcode == 0xe5:
        # PUSH H
        state.push('hl')
    elif opcode == 0xe6:
        # ANI byte
        x = state.a & arg1
        state.cc.z = ((x & 0xff) == 0)
        state.cc.s = ((x & 0x80) != 0)
        state.cc.cy = 0
        state.cc.p = parity(x & 0xff)
        state.a = x
        state.pc += 1
    elif opcode == 0xeb:
        # XCHG
        state.hl, state.de = state.de, state.hl
    elif opcode == 0xf1:
        # POP PSW
        state.pop('psw')
    elif opcode == 0xf5:
        # PUSH PSW
        state.push('psw')
    elif opcode == 0xfb:
        # EI
        state.int_enable = 1
    elif opcode == 0xfe:
        # CPI, D8
        x = state.a - arg1
        state.cc.z = (x & 0xff) == 0
        state.cc.s = (x & 0x80) != 0
        state.cc.p = parity(x & 0xff)
        state.cc.cy = state.a < arg1
        state.pc += 1
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
    return parser.parse_args()


def main():
    args = parse()

    with open(args.bin[0], 'rb') as f:
        state = State(f.read())

    count = 1
    while 1:
        emulate(state, args.debug)
        if args.debug == 3:
            print("Instruction count: %d" % count)
            count += 1


if __name__ == '__main__':
    main()
