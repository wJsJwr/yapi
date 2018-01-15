import sys
from struct import unpack
import json
import time
import re
import traceback
import io

class Parser:

    # PARSER PARAMETER:
    ALLOW_STRING_LENGTH = 100
    ALLOW_REPEATED_NUMBER_COUNT = 10
    GUESS_TIMESTAMP = True


    # parse key:
    # (field_number << 3) | wire_type
    OP_START = 0
    OP_KEY = 1
    OP_VALUE = 2

    # wire type
    # Type	Meaning	Used For
    # 0	Varint	int32, int64, uint32, uint64, sint32, sint64, bool, enum
    # 1	64-bit	fixed64, sfixed64, double
    # 2	Length-delimited	string, bytes, embedded messages, packed repeated fields
    # 3	Start group	groups (deprecated)
    # 4	End group	groups (deprecated)
    # 5	32-bit	fixed32, sfixed32, float
    WT_VAR = 0
    WT_FIX64 = 1
    WT_LD = 2
    WT_GP_START = 3
    WT_GP_END = 4
    WT_FIX32 = 5
    # for convenience
    WT_PRF = 10

    def __init__(self, raw, bi = 0):
        self._bytes = raw
        self._len = len(raw)
        self._cursor = 0
        self._stack = []
        self._last_opr = Parser.OP_START
        self._last_pos = -1
        self._base_indent = bi
        self._current_indent = 0

    def _parse(self):
        # print("?code(%d) = %02x" % (self._cursor, self._bytes[self._cursor]))
        if self._last_pos == self._cursor:
            raise RuntimeError("!!!!Stuck!!!!")
        else:
            self._last_pos = self._cursor

        # print(json.dumps(self._stack))

        if self._last_opr == Parser.OP_START or self._last_opr == Parser.OP_VALUE:
            b = self._varint_decode()
            field_number = (b & 0xf8) >> 3
            wire_type = b & 0x7

            if wire_type == Parser.WT_GP_END:
                if self._stack[-1]['wt'] != Parser.WT_GP_START:
                    print(json.dumps(self._stack))
                    raise AttributeError("Group pair miss.(@%d)" % self._cursor)
                else:
                    self._stack.pop()
                    self._just_print("[%d] Group End" % field_number)
            else:
                if wire_type == Parser.WT_GP_START:
                    self._just_print("[%d] Group Start" % field_number)
                    self._last_opr = Parser.OP_START
                else:
                    self._last_opr = Parser.OP_KEY

                self._stack.append({
                    'fn': field_number,
                    'wt': wire_type
                })

        elif self._last_opr == Parser.OP_KEY:
            # get length or varint
            self._last_opr = Parser.OP_VALUE
            wire_type = self._stack[-1]['wt']
            if wire_type == Parser.WT_VAR:
                cur = self._cursor
                val = self._varint_decode()
                val0 = val
                if val & 0x1 == 1:
                    val = - val
                val >>= 1
                if Parser.GUESS_TIMESTAMP and val0 > 1514736000 and val0 < 1600000000:
                    # guess timestamp
                    self._just_print("[%d] %s (%d or %d) @%d ts?: %s" % (self._stack[-1]['fn'], Parser._to_readable_wt(wire_type), val, val0, cur, time.ctime(val0)))
                else:
                    self._just_print("[%d] %s (%d or %d)" % (self._stack[-1]['fn'], Parser._to_readable_wt(wire_type), val, val0))
                self._stack.pop()
            elif wire_type == Parser.WT_FIX64:
                buf = self._bytes[self._cursor:self._cursor+8]
                self._just_print("[%d] %s (%d or %d or %f)" % (self._stack[-1]['fn'], Parser._to_readable_wt(wire_type), unpack('<Q', buf)[0], unpack('<q', buf)[0], unpack('<d', buf)[0]))
                self._stack.pop()
                self._cursor += 8
            elif wire_type == Parser.WT_FIX32:
                buf = self._bytes[self._cursor:self._cursor+4]
                self._just_print("[%d] %s (%d or %d or %f)" % (self._stack[-1]['fn'], Parser._to_readable_wt(wire_type), unpack('<L', buf)[0], unpack('<l', buf)[0], unpack('<f', buf)[0]))
                self._stack.pop()
                self._cursor += 4
            elif wire_type == Parser.WT_LD:
                length = self._varint_decode()
                # print("?len=%d"%length)
                base_ptr = self._cursor
                parse_success = True
                str_v = ''
                try:
                    str_v = str(self._bytes[self._cursor:self._cursor+length], encoding='utf-8')
                except:
                    parse_success = False

                if parse_success:
                    parse_success = re.match(r"^[\w\s\d:\-!@#$%^&*(\[{}\])_+=\";',./<|>?]*$\Z", str_v, re.M) or len(str_v) <= Parser.ALLOW_STRING_LENGTH

                if parse_success:
                    self._just_print("[%d] %s - String (%s)" % (self._stack[-1]['fn'], Parser._to_readable_wt(wire_type), str_v))

                else:
                    self._just_print("[%d] Packed repeated fields" % (self._stack[-1]['fn']))
                    self._stack.append({'wt':Parser.WT_PRF})
                    if length % 8 == 0:
                        self._just_print('=== May be FIX64 ===')
                        for i in range(0, length, 8):
                            buf = self._bytes[self._cursor+i:self._cursor+i+8]
                            self._just_print("(%d or %d or %f)" % (unpack('<Q', buf)[0], unpack('<q', buf)[0], unpack('<d', buf)[0]))

                    if length % 4 == 0:
                        self._just_print('=== May be FIX32 ===')
                        for i in range(0, length, 4):
                            buf = self._bytes[self._cursor+i:self._cursor+i+4]
                            self._just_print("(%d or %d or %f)" % (unpack('<L', buf)[0], unpack('<l', buf)[0], unpack('<f', buf)[0]))

                    if self._bytes[self._cursor+length-1] & 0x80 != 0:
                        self._just_print('!Should not be Varint. Maybe bytes or Error Here')
                        str_val = ''
                        for i in range(length):
                            str_val += "02x" % self._bytes[self._cursor + i]
                        self._just_print(str_val[:-2])
                    else:
                        numbers = []
                        while self._cursor < base_ptr + length:
                            numbers.append(str(self._varint_decode()))
                        if len(numbers) > Parser.ALLOW_REPEATED_NUMBER_COUNT:
                            self._just_print("!Too many varints(%d), parse as Embedded Messages" % len(numbers))
                            try:
                                inner_parse = Parser(self._bytes[base_ptr:base_ptr+length], self._current_indent)
                                inner_parse.start_parse()
                            except Exception as e:
                                print(e, file=sys.stderr)
                                traceback.print_exc(file=sys.stderr)
                                self._just_print("!!Inner-parse Error!! may be byte-block")
                                pretty = ''
                                for i in range(length):
                                    pretty += "%02x "%(self._bytes[base_ptr + i])
                                    if i % 16 == 15:
                                        self._just_print(pretty)
                                        pretty = ''
                                if pretty != '':
                                    self._just_print(pretty)


                        else:
                            self._just_print('=== May be Varint ===')
                            for n in numbers:
                                self._just_print(n)

                    self._just_print('=== For Debug ===')
                    self._just_print(str_v)
                    self._stack.pop()

                self._cursor = base_ptr + length
                self._stack.pop()


    @staticmethod
    def _to_readable_wt(wire_type):
        if wire_type == Parser.WT_VAR:
            return 'Varint'
        elif wire_type == Parser.WT_FIX64:
            return '64-bit'
        elif wire_type == Parser.WT_LD:
            return 'Length-delimited'
        elif wire_type == Parser.WT_FIX32:
            return '32-bit'

    def _varint_decode(self):
        retval = 0
        i = 0
        while True:
            b = self._bytes[self._cursor]
            c = b & 0x7f
            c <<= 7 * i
            retval |= c
            self._cursor += 1
            i += 1
            if b & 0x80 == 0:
                break                 # last byte

        return retval


    def _just_print(self, s):
        indent = len(self._stack)*4
        if indent > 0 and self._stack[-1]['wt'] != Parser.WT_GP_START:
            indent -= 4

        indent += self._base_indent
        if self._current_indent != indent:
            self._current_indent = indent

        print(s.rjust(len(s) + indent, ' '))

    def start_parse(self):
        # begin to parse protobuf binary
        while self._cursor < self._len:
            self._parse()


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("yapi.py file offset length")
        exit()

    buffer = open(sys.argv[1], 'rb').read()

    # remember to call `CHCP 65001` on windows
    sys.stdout = sys.__stdout__ = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8', line_buffering=True)

    if int(sys.argv[3]) == -1:
        ps = Parser(bytearray(buffer[int(sys.argv[2]):]))
    else:
        ps = Parser(bytearray(buffer[int(sys.argv[2]):int(sys.argv[2])+int(sys.argv[3])]))

    ps.start_parse()
