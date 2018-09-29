import sys
import cpu


def execute_test(fname, success_check):
    # copied from https://github.com/begoon/i8080-core/blob/master/i8080_test.c
    success = 0
    # load test program
    with open(fname, 'rb+') as f:
        data = f.read()
    # init i8080 state for testing purposes
    state = cpu.State(data)
    state.memory = bytearray(0x100) + state.memory
    # inject the rom with RET at position 5 to properly handle CALL 5
    state.memory[5] = 0xC9
    state.pc = 0x100
    print(" Test suite: %s" % fname)

    # start testing
    while 1:
        pc = state.pc
        if state.memory[state.pc] == 0x76:
            print("HLT at %04x" % pc)
            sys.exit(1)
        if pc == 5:
            if state.c == 9:
                i = state.de
                while state.memory[i] != ord('$'):
                    print(chr(state.memory[i]), end='', flush=True)
                    i += 1
                success = 1
            if state.c == 2:
                print(chr(state.e), end='', flush=True)
        cpu.emulate(state)
        if state.pc == 0:
            print("\n Jump to 0000 from %04x" % pc)
            if success_check and not success:
                # failed
                sys.exit(1)
            return


def main():
    # execute_test("cpudiag.bin", 0)
    execute_test("CPUTEST.COM", 0)
    execute_test("TEST.COM", 0)
    execute_test("8080PRE.COM", 1)
    execute_test("8080EX1.COM", 0)
    sys.exit(0)


if __name__ == '__main__':
    main()
