import time
import logging

from sphero_base import init_sphero, Sphero


class SpheroPlus(Sphero):
    def jump(self, speed=70, left=255, right=253, d1=0.1, d2=0.2):
        self.roll(speed, 0)
        time.sleep(d1)
        self.send_raw_motor(1, left, 1, right)
        time.sleep(d2)
        self.send_set_stabilization()
        self.stop()

    def rainbow(self, delay=0.15, repeat=1):
        colors = [(255, 0, 0),
                  (255, 165, 0),
                  (255, 255, 0),
                  (0, 128, 0),
                  (0, 0, 255),
                  (75, 0, 130),
                  (238, 130, 238)]
        for c in colors * repeat:
            self.set_rgb(*c)
            time.sleep(delay)

        self.set_rgb(0, 0, 0)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('address', help='Sphero Bluetooth address')
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG)

    s = init_sphero(args.address, SpheroPlus)

    s.rainbow(repeat=3)

    time.sleep(2.0)

    for _ in range(3):
        s.set_rgb(0, 255, 0)
        time.sleep(0.2)
        s.set_rgb(0, 0, 0)
        time.sleep(0.15)

    time.sleep(2.0)
    s.ping()

    s.roll(100, 0)
    time.sleep(0.3)
    s.stop()
    time.sleep(0.7)

    s.roll(100, 180)
    time.sleep(0.5)
    s.off()
    time.sleep(0.3)
    s.stop()

    s.disconnect()
