class ShiftRegister:

    def __init__(self):
        self._register = 0x0000
        self._offset = 0x0

    def get_register(self):
        return (self._register >> self._offset) & 0xff

    def shift(self, val):
        self._register = (self._register >> 8) | (val << 8)

    def set_offset(self, val):
        self._offset = val & 0x08


class Controller:

    def __init__(self):
        self._p1_reg = 0b00001100
        self._p2_reg = 0b00000001

    def get_p1(self):
        return self._p1_reg

    def get_p2(self):
        return self._p2_reg

    def toggle_start_p1(self):
        self._p1_reg |= 0x02

    def toggle_left_p1(self):
        self._p1_reg |= 0x20

    def toggle_right_p1(self):
        self._p1_reg |= 0x40


class Display:

    def __init__(self):
        self.max_cycles = 2000000/60

    def refresh(self, cycles):
        if cycles >= self.max_cycles:
            return 0xcf, 0xd7


devices = {
    'shft_reg': ShiftRegister(),
    'ctrl': Controller(),
    'dspl': Display(),
}
