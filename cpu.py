from disassembler import disassemble


class Flags:

    def __init__(self):
        self.z = 0
        self.s = 0
        self.p = 0
        self.cy = 0
        self.ac = 0
        self._pad = 3


class State:

    def __init__(self, memory):
        self.memory = bytearray(memory) + bytearray(0x2000)  # ROM + RAM
        self.a = 0
        self.b = 0
        self.c = 0
        self.d = 0
        self.e = 0
        self.h = 0
        self.l = 0
        self.sp = 0
        self.pc = 0
        self.cc = Flags()
        self.int_enable = 0


def emulate(state):

    def parity(n):
        return n % 2 == 0

    opcode, arg1, arg2 = state.memory[state.pc:state.pc + 3]

    disassemble(state.memory, state.pc)
    print("\tC=%d, P=%d, S=%d, Z=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z))
    print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
        state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
    ))

    if opcode == 0x00:
        pass
    elif opcode == 0x01:
        state.c = arg1
        state.b = arg2
        state.pc += 2
    elif opcode == 0x05:     # DCR B
        state.b = (state.b - 1) % 0xff
        if state.b == 0:
            state.cc.z = 1
    elif opcode == 0x06:     # MVI B byte
        state.b = arg1
        state.pc += 1
    elif opcode == 0x0e:     # MVI C byte
        state.c = arg1
        state.pc += 1
    elif opcode == 0x0f:     # RRC / Multiplication
        x = state.a
        state.a = ((x & 1) << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode == 0x11:
        state.d = arg2
        state.e = arg1
        state.pc += 2
    elif opcode == 0x13:
        n = (state.d << 8) | state.e
        n = (n + 1) % 0xffff
        state.d = n >> 8
        state.e = n & 0xff
    elif opcode == 0x19:     # DAD D
        ans1 = (state.d << 8) | state.e
        ans2 = (state.h << 8) | state.l
        ans = ans1 + ans2
        state.cc.cy = ans > 0xffff
        state.h = (ans & 0xffff) >> 8
        state.l = ans & 0xff
    elif opcode == 0x1a:     # LDAX D
        adr = (state.d << 8) | state.e
        state.a = state.memory[adr]
    elif opcode == 0x1f:     # RAR / Division
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode == 0x21:     # LXI H, word
        state.h = arg2
        state.l = arg1
        state.pc += 2
    elif opcode == 0x23:     # INX H
        n = (state.h << 8) | state.l
        n = (n + 1) % 0xffff
        state.h = n >> 8
        state.l = n & 0xff
    elif opcode == 0x26:     # MVI H
        state.h = arg1
        state.pc += 1
    elif opcode == 0x29:     # DAD H
        ans = (state.h << 8) | state.l
        ans <<= 1
        state.cc.cy = ans > 0xffff
        state.h = (ans & 0xffff) >> 8
        state.l = ans & 0xff
    elif opcode == 0x2f:     # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a = state.a ^ 0xff
    elif opcode == 0x31:     # LXI SP
        state.sp = (arg2 << 8) | arg1
        state.pc += 2
    elif opcode == 0x36:     # MVI M byte
        adr = (state.h << 8) | state.l
        state.memory[adr] = arg1
    elif opcode == 0x41:
        state.b = state.c
    elif opcode == 0x42:
        state.b = state.d
    elif opcode == 0x43:
        state.b = state.e
    elif opcode == 0x6f:      # MOV L, A
        state.l = state.a
    elif opcode == 0x77:      # MOV M, A
        adr = (state.h << 8) | state.l
        state.memory[adr] = state.a
    elif opcode == 0x7c:     # MOV A, H
        state.a = state.h
    elif opcode == 0x80:     # ADD B
        ans = int(state.a) + int(state.b)
        # set zero flag if ans is 0
        # 0x00 & 0xff = 0x00 True
        # 0x10 & 0xff = 0x10 False
        state.cc.z = ((ans & 0xff) == 0)
        # set sign flag if left-most bit is 1
        # 0b0001 & 0b1000 = 0b0000 -> False
        # 0b1001 & 0b1000 = 0b1000 -> True
        state.cc.s = ((ans & 0x80) != 0)
        # set carry flag if ans is greater than 0xff
        state.cc.cy = ans > 0xff
        # set parity, ans % 2 == 0: True, else False
        state.cc.p = parity(ans & 0xff)
        # store 2 bytes of the result into register a
        state.a = ans & 0xff
    elif opcode == 0x81:     # ADD C
        ans = int(state.a) + int(state.c)
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode == 0x86:     # ADD M
        # shift eight bits left to concatenate H & L
        adr = (state.h << 8) | state.l
        ans = int(state.a) + int(state.memory[adr])
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode == 0xc1:     # POP B
        state.c = state.memory[state.sp]
        state.b = state.memory[state.sp + 1]
        state.sp += 2
    elif opcode == 0xc2:     # JNZ adr
        if state.cc.z == 0:
            state.pc = (arg2 << 8) | arg1
        else:
            state.pc += 2
    elif opcode == 0xc3:     # JMP adr
        state.pc = (arg2 << 8) | arg1
        return
    elif opcode == 0xc5:     # PUSH B
        state.memory[state.sp - 1] = state.b
        state.memory[state.sp - 2] = state.c
        state.sp -= 2
    elif opcode == 0xc6:     # ADI byte
        ans = int(state.a) + int(arg1)
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
        state.pc += 1
    elif opcode == 0xc9:     # RET
        # set pc to ret adr
        state.pc = state.memory[state.sp] | (state.memory[state.sp + 1] << 8)
        # restore stack pointer
        state.sp += 2
    elif opcode == 0xcd:     # CALL adr
        # return address
        ret = state.pc + 2
        # put high part of ret in pos -1 of the stack
        state.memory[state.sp - 1] = (ret >> 8) & 0xff
        # put low part of ret in pos -2 of the stack
        state.memory[state.sp - 2] = ret & 0xff
        state.sp -= 2
        state.pc = (arg2 << 8) | arg1
        return
    elif opcode == 0xd5:     # PUSH D
        state.memory[state.sp - 1] = state.d
        state.memory[state.sp - 2] = state.e
        state.sp -= 2
    elif opcode == 0xe5:     # PUSH H
        state.memory[state.sp - 1] = state.h
        state.memory[state.sp - 2] = state.l
        state.sp -= 2
    elif opcode == 0xe6:     # ANI byte
        x = state.a & arg1
        state.cc.z = ((x & 0xff) == 0)
        state.cc.s = ((x & 0x80) != 0)
        state.cc.cy = 0
        state.cc.p = parity(x & 0xff)
        state.a = x
        state.pc += 1
    elif opcode == 0xf1:     # POP PSW
        state.a = state.memory[state.sp + 1]
        psw = state.memory[state.sp]
        # copy each meaningful bit from psw to state
        state.cc.z = (0x01 == (psw & 0x01))
        state.cc.s = (0x02 == (psw & 0x02))
        state.cc.p = (0x04 == (psw & 0x04))
        state.cc.cy = (0x08 == (psw & 0x08))
        state.cc.ac = (0x10 == (psw & 0x10))
        state.sp += 2
    elif opcode == 0xf5:     # PUSH PSW
        state.memory[state.sp - 1] = state.a
        psw = state.cc.z
        psw |= state.cc.s << 1
        psw |= state.cc.p << 2
        psw |= state.cc.cy << 3
        psw |= state.cc.ac << 4
        state.memory[state.sp - 2] = psw
        state.sp -= 2
    elif opcode == 0xfe:     # CPI byte
        x = state.a - arg1
        state.cc.z = x == 0
        state.cc.s = (x & 0x80) != 0
        state.cc.p = parity(x & 0xff)
        state.cc.cy = state.a < arg1
        state.pc += 1
    else:
        raise NotImplementedError("opcode %02x is not implemented" % opcode)

    state.pc += 1


def main():
    with open('invaders', 'rb') as f:
        state = State(f.read())

    while 1:
        emulate(state)


if __name__ == '__main__':
    main()
