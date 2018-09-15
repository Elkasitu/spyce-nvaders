

class ShiftRegister:

    def __init__(self):
        self._register = 0x0000
        self._offset = 0

    def get_register(self):
        return (self._register >> (8 - self._offset)) & 0xff

    def shift(self, val):
        self._register = (val << 8) | (self._register >> 8)

    def set_offset(self, val):
        self._offset = val


devices = {
    'shft_reg': ShiftRegister(),
}
