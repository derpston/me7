#!/usr/bin/python

'''
pylibme7
- a very basic python object for interacting with Bosch ME7 ECU's
- requires pylibftdi


Copyright 2013 Ted Richardson.
Distributed under the terms of the GNU General Public License (GPL)
See LICENSE.txt for licensing information.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
--
trichard3000
'''

# stdenv
from __future__ import print_function, division
import time
import logging
import struct
import copy

# 3rd party
import pylibftdi 

logger = logging.getLogger(__name__)

# Commands
StopCommunicating = 0x82
WriteMemoryByAddress = 0x3d
SetupLogging = 0xb7

class Variable(object):
    #https://docs.python.org/2/library/struct.html#format-characters
    _struct_sizes = {1: "B", 2: "H"}

    def __init__(self, name, addr, size=1, unit="?", factor=1, bitmask=None,
        offset=0, signed=False, inverse=False, comment=None):
        
        if size not in [1, 2]:
            raise ValueError("Unsupported variable size (%d)", size)

        if bitmask is None:
            bitmask = (1 << (size * 8)) - 1

        self.name = name
        self.addr = addr
        self.size = size
        self.bitmask = bitmask
        self.unit = unit
        self.factor = factor
        self.offset = offset
        self.signed = signed
        self.inverse = inverse
        self.comment = comment

        self.raw_value = None

    def set(self, raw_value):
        if len(raw_value) != self.size:
            raise ValueError("Wrong number of bytes (%d) for a variable"\
                " of size %d", len(raw_value), self.size)

        self.raw_value = raw_value

    def get(self):
        if self.raw_value is None:
            return None
        else:
            return self._convert(self.raw_value)

    def __repr__(self):
        return "<me7.Variable: %s = %s %s (%s)>" % (
                self.name
            ,   self.get()
            ,   self.unit
            ,   self.comment
            )

    def _convert(self, raw_value):
        """Convert from a list of bytes to the final signed/unsigned value."""
        # We could consider the signed/unsigned type here, but we have to do
        # the signed/unsigned conversion after the bitmask application so we
        # just assume unsigned for now.
        value = struct.unpack(">" + self._struct_sizes[self.size], 
            self._bytestr(raw_value))[0]

        # Apply bitmask.
        value &= self.bitmask

        if self.signed:
            fmt = ">" + self._struct_sizes[self.size]
            # Convert the unsigned value into a signed value by byte-packing
            # it as unsigned, and unpacking it as signed.
            # The struct format characters for signed are lowercase, so just
            # use .lower() to convert the format string.
            value = struct.unpack(fmt.lower(), struct.pack(fmt, value))[0]
        
        if self.inverse:
            value = self.factor / (value - self.offset)
        else:
            value = self.factor * value - self.offset

        return value

    def _bytestr(self, values):
        """Convert a list of ints representing bytes to a string."""
        return "".join([chr(v) for v in values])


class ECU:
    connected = False

    def __init__(self):
        self.port = pylibftdi.Device(mode='b', lazy_open=True)
        self._logged_variables = []

    def bitbang(self, value):
        """Wake up the ECU and tell it we're going to start talking to it.
        We do this by bit-banging a value, with some header/footer bits,
        to the serial port manually. We're aiming for 5 baud."""

        # For the bit widths and timings, see this diagram:
        # https://en.wikipedia.org/wiki/Asynchronous_serial_communication#/media/File:Puerto_serie_Rs232.png
        # The configuration we're emulating here is 8 bits, no parity, one
        # stop bit. (8N1)

        # TODO fix this stupid encapsulation
        value = value[0]

        # Set up the port.
        port = pylibftdi.BitBangDevice()
        port.open()
        port.direction = 0x01
        
        # High for a half second to make the serial line "idle"
        port.port = 1
        time.sleep(.5)

        # Low for one bit-width, the stop bit.
        port.port = 0
        time.sleep(.2)

        # Shift out the byte with appropriate timings.
        for i in range(8):
            port.port = (value >> i) & 1
            time.sleep(.2)

        # Bring the line high to go back to an idle state, and close
        # the port.
        port.port = 1
        port.close()


    def open(self, method = "SLOW-0x11"):
        """Connect to the ECU. Returns a boolean indicating success. Valid 
        values for the `method` parameter are: "SLOW-0x11"
        The default is SLOW-0x11"""
        logging.debug("Attempting ECU connect with method %s" % method)

        # If we're already connected, raise an exception.
        if self.connected:
            raise RuntimeError("Already connected, call .close()"\
            " before reconnecting.")

        if method == "SLOW-0x11":
            # Bit bang the K-line to signal the ECU that we're connecting.
            self.bitbang([0x11])
    
            # Configure the serial port.
            self.port.open()
            self.port.ftdi_fn.ftdi_set_line_property(8, 1, 0)
            self.port.baudrate = 10400
            self.port.flush()

            # Wait for ECU response to the bit banging wakeup call.
            waithex = [0x55, 0xef, 0x8f, 1]
            self.waitfor(waithex)

            # Wait a bit
            # TODO Find out how long this needs to be and why.
            time.sleep(.026)

            self.send([0x70])

            # 0xee means that we're talking to the ECU
            waithex = [0xee, 1]
            response = self.waitfor(waithex)
            if response[0] == True:
                self.connected = True
            
            return self.connected
        else:
            raise RuntimeError("Unknown connection method: %s" % method)

    def waitfor(self, wf):
        # This was used for debugging and really is only used for the init at this point.
        # wf should be a list with the timeout in the last element
        self.wf = wf
        isfound = False
        idx = 0
        foundlist = []
        capturebytes = []
        to = self.wf[-1]
        timecheck = time.time()
        while (time.time() <= (timecheck + to)) & (isfound == False):
            try:
                recvbyte = self.recvraw(1)
                if recvbyte != "":
                    recvdata = ord(recvbyte)
                    capturebytes = capturebytes + [recvdata]
                    if recvdata == self.wf[idx]:
                        foundlist = foundlist + [recvdata]
                        idx = idx + 1
                    else:
                        foundlist = []
                        idx = 0
                    if idx == len(self.wf) - 1:
                        isfound = True
            except:
                print('error')
                break
        return [isfound, foundlist, capturebytes]

    def send(self, buf):
        """Writes the list of bytes in `buf` to the serial port."""
        self.port.write("".join([chr(b) for b in buf]))

    def recvraw(self, bytes):
        self.bytes = bytes
        recvdata = self.port.read(self.bytes)
        return recvdata

    def recv(self, bytes):
        self.bytes = bytes
        isread = False
        while isread == False:
            recvbyte = self.port.read(self.bytes)
            if recvbyte != "":
                recvdata = recvbyte
                isread = True
        return recvdata

    def sendCommand(self, buf):
        """Wraps raw KWP command in a length byte and a checksum byte and
        hands it to send(). Returns a boolean indicating whether
        validateCommand was satisfied with the response from the ECU."""
        sendbuf = [len(buf)]
        sendbuf.extend(buf)
        sendbuf.append(self.checksum(sendbuf))

        self.send(sendbuf)
        return self._validateCommand(sendbuf)

    def _validateCommand(self, command):
        # Every KWP command is echoed back.  This clears out these bytes.
        self.command = command
        cv = True
        for i in range(len(self.command)):
            recvdata = self.recv(1)
            if ord(recvdata) != self.command[i]:
                cv = cv & False
        return cv

    def checksum(self, buf):
        """Returns an int that is the KWP2000 checksum of a list of ints."""
        return (sum(buf) & 0xff) % 0xff

    def getresponse(self):
        # gets a properly formated KWP response from a command and returns the
        # data.
        numbytes = 0
        # This is a hack because sometimes responses have leading 0x00's.  Why?
        # This removes them.
        while numbytes == 0:
            numbytes = ord(self.recv(1))
        gr = [numbytes]
        logger.debug("Get bytes: " + hex(numbytes))
        for i in range(numbytes):
            recvdata = ord(self.recv(1))
            logger.debug("Get byte" + str(i) + ": " + hex(recvdata))
            gr = gr + [recvdata]
        checkbyte = self.recv(1)
        logger.debug(gr)
        logger.debug("GR: " + hex(ord(checkbyte)) +
                     "<-->" + hex(self.checksum(gr)))
        # TODO Enforce the bloody checksum
        # TODO Don't return the checksum with the response
        return (gr + [ord(checkbyte)])

    def readecuid(self, paramdef):
        # KWP2000 command to pull the ECU ID
        self.paramdef = paramdef
        reqserviceid = [0x1A]
        sendlist = reqserviceid + self.paramdef
        logger.debug(sendlist)
        self.sendCommand(sendlist)
        response = self.getresponse()
        logger.debug(response)
        return response

    def close(self):
        """Disconnects from the ECU."""
        if self.connected:
            self.sendCommand([StopCommunicating])
            response = self.getresponse()
            self.port.close()
            return response
        else:
            raise RuntimeError("Already disconnected.")

    def startdiagsession(self, bps):
        # KWP2000 setup that sets the baud for the logging session
        self.bps = bps
        startdiagnosticsession = [0x10]
        setbaud = [0x86]  # Is this the actual function of 0x86?
    #   if self.bps == 10400:
    #      bpsout = [ 0x?? ]
    #   if self.bps == 14400:
    #      bpsout = [ 0x?? ]
        if self.bps == 19200:
            bpsout = [0x30]
        if self.bps == 38400:
            bpsout = [0x50]
        if self.bps == 56000:
            bpsout = [0x63]
        if self.bps == 57600:
            bpsout = [0x64]
    #   if self.bps == 125000:
    #      bpsout = [ 0x?? ]
        sendlist = startdiagnosticsession + setbaud + bpsout
        self.sendCommand(sendlist)
        response = self.getresponse()
        self.port.baudrate = self.bps
        time.sleep(1)
        return response

    def accesstimingparameter(self, params):
        # KWP2000 command to access timing parameters
        self.params = params
        accesstiming_setval = [0x083, 0x03]
        accesstiming = accesstiming_setval + self.params
        sendlist = accesstiming
        self.sendCommand(sendlist)
        response = self.getresponse()
        return response

    def readmembyaddr(self, readvals):
        # Function to read an area of ECU memory.
        self.readvals = readvals
        rdmembyaddr = [0x23]
        sendlist = rdmembyaddr + self.readvals
        logger.debug("readmembyaddr() sendlist: " + sendlist)
        self.sendCommand(sendlist)
        response = self.getresponse()
        logger.debug("readmembyaddr() response: " + response)
        return response

    def writemembyaddr(self, addr, value):
        """Writes `value` to memory at address `addr`. `value` is expected
        to be a list of ints, each representing one byte."""
        cmd = [WriteMemoryByAddress] + self._splitAddr(addr) + [len(value)] + value
        self.sendCommand(cmd)
        response = self.getresponse()
        return response

    def testerpresent(self):
        # KWP2000 TesterPresent command
        tp = [0x3E]
        self.sendCommand(tp)
        response = self.getresponse()
        return response

    def prepareLogVariables(self, *variables):
        """Configures the ECU with a list of memory addresses, whose values
        will be read later with getlogrecord"""


        # 0x03 probably means to expect three byte addresses. Untested.
        cmd = [SetupLogging, 0x03]

        for var in variables:
            # Convert the integer address value to a list of three bytes and
            # add it to the pending command.
            addr = self._splitAddr(var.addr)

            # Telling the ECU we want to read two bytes is done by adding
            # 0x40 to the most significant byte.
            if var.size == 2:
                addr[0] += 0x40 

            # Add the address to the command.
            cmd.extend(addr)

        # Save a copy of the variable list, which will be used later by
        # getLogRecord to parse the results.
        self._logged_variables = variables

        self.sendCommand(cmd)
        return self.getresponse()

    def getLogValues(self):
        """Fetches a value for each configured variable from the ECU and
        returns a dict of Variables, keyed by the variable name."""
        raw_result = self.getlogrecord()

        # Strip header and checksum.
        length = raw_result[0]
        # TODO Find out why this always seems to be 0xf7. Is it just
        # indicating success, or something else?
        unknown = raw_result[1]
        checksum = raw_result[-1]
        result = raw_result[2:-1]

        response = {}
        index = 0
        for var in self._logged_variables:
            # Slice out the bytes relevant to this variable.
            raw_bytes = result[index:index + var.size]

            # Make a copy of the variable, give it the raw bytes, and add
            # it to the response dict.
            copied_var = copy.copy(var)
            copied_var.set(raw_bytes)
            response[copied_var.name] = copied_var

            index += var.size
        return response
    
    def getlogrecord(self):
        """Returns a list of bytes representing the values of the memory
        addresses previously added to the logging list."""
        self.sendCommand([0xb7])
        return self.getresponse()
    
    def _splitAddr(self, addr):
        """Takes an integer memory address in `addr`, assumes a maximum
        three byte length, and returns a list of three ints corresponding
        to these three bytes, most significant first."""
        return [ord(b) for b in struct.pack(">L", addr)[1:]]
