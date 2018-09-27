from collections import deque
from devices import devices

import pygame
import sys


class Bus(object):

    def __init__(self):
        self.device_map_write = {
            0x02: devices['shft_reg'].set_offset,
            0x03: int,  # dummy
            0x04: devices['shft_reg'].shift,
            0x05: float,  # dummy
            0x06: int,  # dummy
        }

        self.device_map_read = {
            0x01: devices['ctrl'].get_p1,
            0x02: devices['ctrl'].get_p2,
            0x03: devices['shft_reg'].get_register,
        }

        self.interrupts = deque()

    def write(self, adr, val):
        self.device_map_write[adr](val)

    def read(self, adr):
        return self.device_map_read[adr]()

    def loop(self, cycles):
        refresh = devices['dspl'].refresh(cycles)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    sys.exit(0)
                if event.key == pygame.K_LEFT:
                    devices['ctrl'].toggle_left_p1()
                elif event.key == pygame.K_RIGHT:
                    devices['ctrl'].toggle_right_p1()
                elif event.key == pygame.K_RETURN:
                    devices['ctrl'].toggle_start_p1()

        if refresh:
            self.interrupts.extend(refresh)
            # CPU clock tick
            return True


bus = Bus()
