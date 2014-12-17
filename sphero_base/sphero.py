import socket
import logging
import struct
import time
from collections import namedtuple


LOG_CATEGORY = 'sphero'
log = logging.getLogger(LOG_CATEGORY)

DID_CORE = 0x00
DID_SPHERO = 0x02

CMD_PING = 0x01
CMD_VERSIONING = 0x02
CMD_SLEEP = 0x22

CMD_SET_HEADING = 0x01
CMD_SET_STABILIZATION = 0x02
CMD_READ_LOCATOR = 0x15
CMD_SET_RGB = 0x20
CMD_SET_BACKLIGHT = 0x21
CMD_ROLL = 0x30
CMD_RAW_MOTOR = 0x33


def make_response(fmt, cls):
    def make(data):
        return cls(*struct.unpack(fmt, data))
    return make

Version = namedtuple('Version', ['recv', 'mdl', 'hw', 'msa_ver', 'msa_rev',
                                 'bl', 'bas', 'macro', 'api_maj', 'api_min'])
Location = namedtuple('Location', ['x', 'y', 'vel_x', 'vel_y', 'sog'])


class BoundCounter:
    def __init__(self, start=0, boundary=0x0100):
        self.n = start
        self.mod = boundary

    def __call__(self):
        return self.n

    def next(self):
        self.n = (self.n + 1) % self.mod
        return self.n


def gen_checksum(*msg_bytes):
    return ~sum(msg_bytes) % 256


class Connection:
    def __init__(self, address, port):
        self._socket = None
        self.address = address
        self.port = port
        self._buffer = b''

    def connect(self, repeat=1):
        connected = False

        for _ in range(repeat):
            try:
                s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM,
                                  socket.BTPROTO_RFCOMM)
                s.connect((self.address, self.port))
                self._socket = s
                connected = True
                break
            except OSError as error:
                log.warning(error)
                s.close()

        if not connected:
            log.error('Failed to connect after %d attempts.', repeat)
            s.close()
        else:
            log.info('Connected: %r', self._socket)
            log.debug('socket timeout: %r', self._socket.gettimeout())

        return connected

    def disconnect(self):
        if not self._socket:
            raise RuntimeError('Not connected')

        self._socket.close()
        self._socket = None

    def send(self, data, flags=None):
        if not self._socket:
            raise RuntimeError('Not connected')

        args = (data,)
        if flags is not None:
            args = (data, flags)

        return self._socket.send(*args)

    def recv(self, buffersize, flags=None):
        if not self._socket:
            raise RuntimeError('Not connected')

        args = (buffersize,)
        if flags is not None:
            args = (buffersize, flags)

        return self._socket.recv(*args)

    def read(self, size):
        blen = len(self._buffer)
        to_read = size - blen
        while to_read > 0:
            data = self._socket.recv(to_read)
            if not data:
                self.error('Connection closed')
                return
            to_read -= len(data)
            self._buffer += data

        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data

    def flush(self):
        try:
            data = self._socket.recv(1024, socket.MSG_DONTWAIT)
        except Exception as e:
            log.error(e)
        else:
            log.warning('flushed input (%r)', data)


class ResponseError(Exception):
    pass


class SpheroRaw:
    connect_retries = 10

    def __init__(self, address, port=1):
        self._conn = Connection(address, port)
        self.seq = BoundCounter()

    def connect(self):
        return self._conn.connect(self.connect_retries)

    def disconnect(self):
        return self._conn.disconnect()

    def send_msg(self, did, cid, data=None, answer=False, reset=True, seq=None):
        sop1 = 0xff
        sop2 = 0xfc

        if reset:
            sop2 |= 0x02

        if answer:
            sop2 |= 0x01

            if seq is None:
                seq = self.seq.next()

        if seq is None:
            seq = 0x00

        if data is None:
            data = b''

        dlen = len(data) + 1
        chk = gen_checksum(did, cid, seq, dlen, *data)

        self._conn.send(bytes([sop1, sop2, did, cid, seq, dlen]) +
                          data + bytes([chk]))

    def recv_msg(self, make=None):
        data = self._conn.read(5)

        if not data:
            log.warning('Disconnected')
            self._conn.disconnect()
            return None

        sop1, sop2, b3, b4, b5 = data
        if sop1 != 0xff or (sop2 & 0xfe) != 0xfe:
            raise ResponseError('Invalid SOP: 0x%02x, 0x%02x' % (sop1, sop2))

        dlen = b5
        if sop2 == 0xfe:
            dlen |= b4 << 8

        # at least 1 byte is expected (the checksum)
        if dlen < 1:
            raise ResponseError('Invalid body length: %d' % (dlen,))

        body = self._conn.read(dlen)

        if not body:
            log.warning('Disconnected (reading body)')
            self._conn.disconnect()
            return None

        content = body[:-1]
        chk = gen_checksum(b3, b4, b5, *body[:-1])
        if chk == body[-1]:
            if make is not None:
                content = make(content)
        else:
            log.warning('Message checksum incorrect: %r', data + body)
            raise ResponseError('Invalid checksum')

        return (sop2, b3, b4, b5, chk, content, body[-1])

    def send_ping(self):
        self.send_msg(DID_CORE, CMD_PING, answer=True)
        return self.recv_msg()

    def send_get_version(self):
        self.send_msg(DID_CORE, CMD_VERSIONING, answer=True)
        return self.recv_msg(make_response('!10B', Version))

    def send_sleep(self):
        data = bytes(5)
        self.send_msg(DID_CORE, CMD_SLEEP, data)

    def send_set_heading(self, heading):
        data = struct.pack('!H', heading % 360)
        self.send_msg(DID_SPHERO, CMD_SET_HEADING, data)

    def send_set_stabilization(self, enable=True):
        data = bytes([0x01 if enable else 0x00])
        self.send_msg(DID_SPHERO, CMD_SET_STABILIZATION, data)

    def send_read_locator(self):
        self.send_msg(DID_SPHERO, CMD_READ_LOCATOR, answer=True)
        return self.recv_msg(make_response('!hhhhH', Location))

    def send_set_rgb(self, r, g, b, save=False):
        data = bytes([r, g, b, 0x01 if save else 0x00])
        self.send_msg(DID_SPHERO, CMD_SET_RGB, data)

    def send_set_backlight(self, value):
        data = bytes([value])
        self.send_msg(DID_SPHERO, CMD_SET_BACKLIGHT, data)

    def send_roll(self, speed, heading, state=0x01):
        data = struct.pack('!BHB', speed, heading % 360, state)
        self.send_msg(DID_SPHERO, CMD_ROLL, data)

    def send_raw_motor(self, left_mode, left_power, right_mode, right_power):
        data = bytes([left_mode, left_power, right_mode, right_power])
        self.send_msg(DID_SPHERO, CMD_RAW_MOTOR, data)


class Sphero(SpheroRaw):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_heading = (0, 0, 0)

    def roll(self, speed, heading, state=1):
        self.last_heading = heading
        return self.send_roll(speed, heading, state)

    def off(self):
        return self.roll(0, self.last_heading, 0)

    def stop(self):
        self.roll(0, 0, 0)

    ping = SpheroRaw.send_ping
    set_rgb = SpheroRaw.send_set_rgb
    set_backlight = SpheroRaw.send_set_backlight


def init_sphero(addr, sphero_class=Sphero):
    s = sphero_class(addr)
    connected = s.connect()
    if not connected:
        raise RuntimeError('Could not establish connection')

    ping_clean = False

    retries = 5
    while retries > 0:
        retries -= 1
        try:
            s.send_ping()
            ping_clean = True
            if retries > 1:
                retries = 1
        except ResponseError as e:
            log.error(e)
            s._conn.flush()

    if not ping_clean:
        log.error('Failed to clean the receive channel')
    else:
        log.debug('Receive channel clean')

    return s
