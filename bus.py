from devices import devices


class Bus(object):

    def __init__(self):
        self.device_map_write = {
            0x03: devices['shft_reg'].set_offset,
            0x04: devices['shft_reg'].shift,
        }

        self.device_map_read = {
            0x03: devices['shft_reg'].get_register,
        }

    def write(self, adr, val):
        self.device_map_write[adr](val)

    def read(self, adr):
        return self.device_map_read[adr]()


bus = Bus()
