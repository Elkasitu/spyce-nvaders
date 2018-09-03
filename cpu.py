from collections import namedtuple

Flags = namedtuple("Flags", "z s p cy ac pad")
State = namedtuple("State", "a b c d e h l sp pc memory cc int_enable")


def emulate(state):

    def parity(n):
        pass

    opcode = state.memory[state.pc]

    if opcode[0] == 0x01:
        state.c = opcode[1]
        state.b = opcode[2]
        state.pc += 2
    elif opcode[0] == 0x0f:     # RRC / Multiplication
        x = state.a
        state.a = ((x & 1) << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode[0] == 0x1f:     # RAR / Division
        x = state.a
        state.a = (state.cc.cy << 7) | (x >> 1)
        state.cc.cy = (x & 1) == 1
    elif opcode[0] == 0x2f:     # CMA
        # python's ~ operator uses signed not, we want unsigned not
        state.a = state.a ^ 0xff
    elif opcode[0] == 0x41:
        state.b = state.c
    elif opcode[0] == 0x42:
        state.b = state.d
    elif opcode[0] == 0x43:
        state.b = state.e
    elif opcode[0] == 0x80:     # ADD B
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
    elif opcode[0] == 0x81:     # ADD C
        ans = int(state.a) + int(state.c)
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode[0] == 0x86:     # ADD M
        # shift eight bits left to concatenate H & L
        adr = (state.h << 8) | state.l
        ans = int(state.a) + int(state.memory[adr])
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
    elif opcode[0] == 0xc1:     # POP B
        state.c = state.memory[state.sp]
        state.b = state.memory[state.sp + 1]
        state.sp += 2
    elif opcode[0] == 0xc2:     # JNZ adr
        if state.cc.z == 0:
            state.pc = (opcode[2] << 8) | opcode[1]
        else:
            state.pc += 2
    elif opcode[0] == 0xc3:     # JMP adr
        state.pc = (opcode[2] << 8) | opcode[1]
    elif opcode[0] == 0xc5:     # PUSH B
        state.memory[state.sp - 1] = state.b
        state.memory[state.sp - 2] = state.c
        state.sp -= 2
    elif opcode[0] == 0xc6:     # ADI byte
        ans = int(state.a) + int(opcode[1])
        state.cc.z = ((ans & 0xff) == 0)
        state.cc.s = ((ans & 0x80) != 0)
        state.cc.cy = ans > 0xff
        state.cc.p = parity(ans & 0xff)
        state.a = ans & 0xff
        state.pc += 1
    elif opcode[0] == 0xc9:     # RET
        # set pc to ret adr
        state.pc = state.memory[state.sp] | (state.memory[state.sp + 1] << 8)
        # restore stack pointer
        state.sp += 2
    elif opcode[0] == 0xcd:     # CALL adr
        # return address
        ret = state.pc + 2
        # put high part of ret in pos -1 of the stack
        state.memory[state.sp - 1] = (ret >> 8) & 0xff
        # put low part of ret in pos -2 of the stack
        state.memory[state.sp - 2] = ret & 0xff
        state.sp -= 2
        state.pc = (opcode[2] << 8) | opcode[1]
    elif opcode[0] == 0xe6:     # ANI byte
        x = state.a & opcode[1]
        state.cc.z = ((x & 0xff) == 0)
        state.cc.s = ((x & 0x80) != 0)
        state.cc.cy = 0
        state.cc.p = parity(x, 8)
        state.a = x
        state.pc += 1
    elif opcode[0] == 0xf1:     # POP PSW
        state.a = state.memory[state.sp + 1]
        psw = state.memory[state.sp]
        # copy each meaningful bit from psw to state
        state.cc.z = (0x01 == (psw & 0x01))
        state.cc.s = (0x02 == (psw & 0x02))
        state.cc.p = (0x04 == (psw & 0x04))
        state.cc.cy = (0x08 == (psw & 0x08))
        state.cc.ac = (0x10 == (psw & 0x10))
        state.sp += 2
    elif opcode[0] == 0xf5:     # PUSH PSW
        state.memory[state.sp - 1] = state.a
        psw = state.cc.z
        psw |= state.cc.s << 1
        psw |= state.cc.p << 2
        psw |= state.cc.cy << 3
        psw |= state.cc.ac << 4
        state.memory[state.sp - 2] = psw
        state.sp -= 2
    elif opcode[0] == 0xfe:     # CPI byte
        x = state.a - opcode[1]
        state.cc.z = x == 0
        state.cc.s = (x & 0x80) != 0
        state.cc.p = parity(x, 8)
        state.cc.cy = state.a < opcode[1]
        state.pc += 1

    state.pc += 1
