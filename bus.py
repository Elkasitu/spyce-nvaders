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

        if refresh:
            self.interrupts.extend(refresh)
            # CPU clock tick
            return True
        return False

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                devices['ctrl'].reset()
                if event.key == pygame.K_ESCAPE:
                    sys.exit(0)
                if event.key == pygame.K_LEFT:
                    devices['ctrl'].mv_left_p1()
                elif event.key == pygame.K_RIGHT:
                    devices['ctrl'].mv_right_p1()
                elif event.key == pygame.K_RETURN:
                    devices['ctrl'].start_p1()
                elif event.key == pygame.K_BACKSPACE:
                    devices['ctrl'].start_p2()
                elif event.key == pygame.K_LCTRL:
                    devices['ctrl'].shoot_p1()
                elif event.key == pygame.K_a:
                    devices['ctrl'].mv_left_p2()
                elif event.key == pygame.K_d:
                    devices['ctrl'].mv_right_p2()
                elif event.key == pygame.K_SPACE:
                    devices['ctrl'].shoot_p2()
                elif event.key == pygame.K_c:
                    devices['ctrl'].add_credit()


bus = Bus()
