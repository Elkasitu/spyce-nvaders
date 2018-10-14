import argparse
import sys
import cpu
import disassembler


def execute_test(fname, success_check, debug=0):
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
        if debug:
            disassembler.disassemble(state.memory, state.pc)
        if debug > 1:
            print("\tC=%d, P=%d, S=%d, Z=%d, AC=%d\n" % (state.cc.cy, state.cc.p, state.cc.s, state.cc.z, state.cc.ac))
            print("\tA %02x B %02x C %02x D %02x E %02x H %02x L %02x SP %04x\n" % (
                state.a, state.b, state.c, state.d, state.e, state.h, state.l, state.sp
            ))
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Emulate programs for the Intel 8080 processor"
    )
    parser.add_argument('-d', '--debug', action='count', default=0,
                        help="Display debug output, can be specified up to 3 times")
    return parser.parse_args()


def main():
    args = parse_args()
    execute_test("cpudiag.bin", 0, args.debug)
    # execute_test("CPUTEST.COM", 0, args.debug)
    # execute_test("TEST.COM", 0, args.debug)
    # execute_test("8080PRE.COM", 1, args.debug)
    # execute_test("8080EX1.COM", 0, args.debug)
    sys.exit(0)


if __name__ == '__main__':
    main()
