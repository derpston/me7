from unittest import TestCase
import mock
import me7
import StringIO


class TestECUExists(TestCase):
    """A pointless test, intended to test the test infrastructure and
    provide an example to build on."""

    def test_ecu_class_exists(self):
        self.assertTrue(getattr(me7, 'ECU'))


class TestChecksum(TestCase):
    """A KWP2000 checksum is the 8 bit sum of all bytes."""

    def setUp(self):
        with mock.patch("pylibftdi.Device"):
            self.ecu = me7.ECU()

    def test_checksum_empty(self):
        self.assertEqual(self.ecu.checksum([]), 0)
    
    def test_checksum_basic(self):
        self.assertEqual(self.ecu.checksum([0x01]), 1)
        self.assertEqual(self.ecu.checksum([0x01, 0x00]), 1)
        self.assertEqual(self.ecu.checksum([0x01, 0x01]), 2)

    def test_checksum_wrap(self):
        self.assertEqual(self.ecu.checksum([0xff]), 0)
        self.assertEqual(self.ecu.checksum([0xfe]), 0xfe)
        self.assertEqual(self.ecu.checksum([0xfe, 0x01]), 0)
        self.assertEqual(self.ecu.checksum([0xdd, 0xdd]), 186)


class TestCommandValidate(TestCase):
    """KWP2000 commands are echoed back and should be checked."""

    def setUp(self):
        with mock.patch("pylibftdi.Device"):
            self.ecu = me7.ECU()

    def test_commandValidate(self):
        with mock.patch("me7.ECU.recv", return_value = "\x00"):
            self.assertTrue(self.ecu._validateCommand([0x00]))
    
        with mock.patch("me7.ECU.recv", return_value = "\x00"):
            self.assertFalse(self.ecu._validateCommand([0x01]))

class TestSendCommand(TestCase):
    """KWP2000 commands are wrapped in a length byte and a checksum byte."""

    def setUp(self):
        with mock.patch("pylibftdi.Device"):
            self.ecu = me7.ECU()

    @mock.patch("me7.ECU._validateCommand", return_value = True)
    @mock.patch("me7.ECU.checksum", return_value = 0x00)
    def test_sendCommand(self, checksum, validate):
        with mock.patch("me7.ECU.send") as send:
            self.assertTrue(self.ecu.sendCommand([0x00]))
            send.assert_called_once_with([1, 0, 0])
        
        with mock.patch("me7.ECU.send") as send:
            self.assertTrue(self.ecu.sendCommand([0x01]))
            send.assert_called_once_with([1, 1, 0])
 
        checksum.return_value = 1
        with mock.patch("me7.ECU.send") as send:
            self.assertTrue(self.ecu.sendCommand([0x01]))
            send.assert_called_once_with([1, 1, 1])

        checksum.return_value = 0
        with mock.patch("me7.ECU.send") as send:
            self.assertTrue(self.ecu.sendCommand([0x01, 0x01, 0x01]))
            send.assert_called_once_with([3, 1, 1, 1, 0])


class TestSend(TestCase):
    """Sends some bytes out the serial port."""

    def setUp(self):
        with mock.patch("pylibftdi.Device"):
            self.ecu = me7.ECU()

    def test_send(self):
        # The port should be a file-like object.
        self.ecu.port = StringIO.StringIO()
        self.ecu.send([0x00])
        self.assertEqual("\x00", self.ecu.port.getvalue())
        
        self.ecu.port = StringIO.StringIO()
        self.ecu.send([0x00, 0x01, 0xff])
        self.assertEqual("\x00\x01\xff", self.ecu.port.getvalue())


class TestBitBang(TestCase):
    """Manually sends (bitbangs) a byte out of the serial port at a specified
    and very slow baud rate. This has the effect of signalling to the ECU that
    we'd like to communicate with it."""

    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    @mock.patch("pylibftdi.BitBangDevice.port", new_callable=mock.PropertyMock)
    @mock.patch("pylibftdi.BitBangDevice.direction", new_callable=mock.PropertyMock)
    @mock.patch("pylibftdi.BitBangDevice.close")
    @mock.patch("pylibftdi.BitBangDevice.open")
    @mock.patch("time.sleep")
    def test_bitbang(self, sleep, bbd_open, bbd_close, bbd_direction, bbd_port):
        test_value = 0xaa
        self.ecu.bitbang([test_value])

        port_values = [call[0][0] for call in bbd_port.call_args_list]
        sleep_values = [call[0][0] for call in sleep.call_args_list]

        # Starts with high, then low, and ends high.
        self.assertEqual(port_values[0], 1)
        self.assertEqual(port_values[1], 0)
        self.assertEqual(port_values[-1], 1)

        value_bits = port_values[2:-1]
        reconstructed_value = int("0b" + "".join(map(lambda b: str(b), value_bits)), 2)
        # Invert reconstructed value, we're supposed to transmit the inverse
        # because that's how RS232 voltage levels work:
        # https://en.wikipedia.org/wiki/RS-232#Voltage_levels
        reconstructed_value ^= 0xff
        self.assertEqual(test_value, reconstructed_value)

        # Check the bit timings. Half second to start, 0.2s between each bit.
        self.assertEqual(sleep_values[0], 0.5)
        for value in sleep_values[2:]:
            self.assertEqual(value, 0.2)

        bbd_open.assert_called_with() # called twice
        bbd_close.assert_called_once_with()
        bbd_direction.assert_called_with(1)


class TestOpen(TestCase):
    """Connects to an ECU."""

    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    def test_bad_method(self):
        with self.assertRaises(RuntimeError):
            self.ecu.open("not a valid connection method")

    def test_bad_order(self):
        with self.assertRaises(RuntimeError):
            self.ecu.open("not a valid connection method")

    @mock.patch("me7.ECU.bitbang")
    @mock.patch("me7.ECU.waitfor", side_effect=[[True], [True]])
    @mock.patch("time.sleep")
    def test_connect(self, sleep, waitfor, bitbang):
        returnvalue = self.ecu.open("SLOW-0x11")
        self.assertTrue(returnvalue)

        self.ecu.port.open.assert_called_once_with()
        self.ecu.port.ftdi_fn.ftdi_set_line_property.assert_called_once_with(8, 1, 0)
        self.assertEqual(self.ecu.port.baudrate, 10400)
        self.ecu.port.flush.assert_called_once_with()
    

class TestSetupLogRecord(TestCase):
    """Tells the ECU which memory addresses you want to read later."""

    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    @mock.patch("me7.ECU.sendCommand")
    @mock.patch("me7.ECU.getresponse")
    def test_preparelogvariables(self, getresponse, sendCommand):
        var1 = me7.Variable("foo", 0x00)
        self.ecu.prepareLogVariables(var1)
        sendCommand.assert_called_with([0xb7, 0x03, 0x00, 0x00, 0x00])

        var2 = me7.Variable("foo", 0x010203)
        self.ecu.prepareLogVariables(var2)
        sendCommand.assert_called_with([0xb7, 0x03, 0x01, 0x02, 0x03])
        
        self.ecu.prepareLogVariables(var1, var2)
        sendCommand.assert_called_with([0xb7, 0x03, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03])

class TestGetLogRecord(TestCase):
    """Requests values for all log records used previously in setuplogrecord"""

    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    @mock.patch("me7.ECU.sendCommand")
    @mock.patch("me7.ECU.getresponse")
    def test_connect(self, getresponse, sendCommand):
        self.ecu.getlogrecord()
        sendCommand.assert_called_with([0xb7])


class TestWriteMemByAddr(TestCase):
    """Writes arbitrary data to memory."""

    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    @mock.patch("me7.ECU.sendCommand")
    @mock.patch("me7.ECU.getresponse")
    @mock.patch("me7.logger")
    def test_writemembyaddr(self, logger, getresponse, sendCommand):
        self.ecu.writemembyaddr(0x00e228, [0x00, 0x3a, 0xe1, 0x00])
        sendCommand.assert_called_with([0x3d, 0x00, 0xe2, 0x28, 0x04, 0x00, 0x3a, 0xe1, 0x00])

class TestSplitBytes(TestCase):
    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    def test_splitbytes(self):
        self.assertEqual(self.ecu._splitAddr(0x123456), [0x12, 0x34, 0x56])
        self.assertEqual(self.ecu._splitAddr(0x000056), [0x00, 0x00, 0x56])
        self.assertEqual(self.ecu._splitAddr(0x56), [0x00, 0x00, 0x56])

class TestVariable(TestCase):
    def test_factor_offset(self):
        var = me7.Variable("foo", 0x00)
        self.assertEqual(var._convert([1]), 1)
        
        var = me7.Variable("foo", 0x00, factor=2)
        self.assertEqual(var._convert([1]), 2)

        var = me7.Variable("foo", 0x00, offset=50)
        self.assertEqual(var._convert([1]), -49)

        var = me7.Variable("foo", 0x00, factor=2, offset=10)
        self.assertEqual(var._convert([1]), -8)
        
        var = me7.Variable("foo", 0x00, factor=2, offset=-10)
        self.assertEqual(var._convert([1]), 12)
        
        var = me7.Variable("foo", 0x00, factor=2, offset=-10)
        self.assertEqual(var._convert([5]), 20)
        
    def test_bitmask(self):
        var = me7.Variable("foo", 0x00, bitmask=0)
        self.assertEqual(var._convert([0xff]), 0)
        
        var = me7.Variable("foo", 0x00, bitmask=1)
        self.assertEqual(var._convert([0xff]), 1)
        
        var = me7.Variable("foo", 0x00, bitmask=0b10)
        self.assertEqual(var._convert([0xff]), 2)
        
        var = me7.Variable("foo", 0x00, bitmask=0b1000)
        self.assertEqual(var._convert([0xff]), 8)
        
        var = me7.Variable("foo", 0x00, size=2)
        self.assertEqual(var._convert([0xff, 0x00]), 0xff00)

        var = me7.Variable("foo", 0x00, bitmask=0b1000, size=2)
        self.assertEqual(var._convert([0xff, 0x00]), 0)
        
        var = me7.Variable("foo", 0x00, bitmask=1 << 12, size=2)
        self.assertEqual(var._convert([0xff, 0x00]), 4096)

    def test_convert(self):
        var = me7.Variable("foo", 0x00)
        self.assertEqual(var._convert([0x00]), 0)
        
        var = me7.Variable("foo", 0x00)
        self.assertEqual(var._convert([0x01]), 1)

        var = me7.Variable("foo", 0x00, size=2)
        self.assertEqual(var._convert([0x00, 0x01]), 1)
        
        var = me7.Variable("foo", 0x00, size=2)
        self.assertEqual(var._convert([0x01, 0x00]), 256)
        
        var = me7.Variable("foo", 0x00, signed=True)
        self.assertEqual(var._convert([0x01]), 1)
       
        var = me7.Variable("foo", 0x00, signed=True)
        self.assertEqual(var._convert([0xff]), -1)
        
        var = me7.Variable("foo", 0x00, signed=True, size=2)
        self.assertEqual(var._convert([0xff, 0xff]), -1)
        
        var = me7.Variable("foo", 0x00, signed=True, size=2)
        self.assertEqual(var._convert([0xff, 0x00]), -256)

    def test_set(self):
        var = me7.Variable("foo", 0x00)
        var.set([0x00])
        self.assertEqual(var.get(), 0)

        var = me7.Variable("foo", 0x00)
        self.assertEqual(var.get(), None)
        
        var = me7.Variable("foo", 0x00)
        with self.assertRaises(ValueError):
            var.set([0x00, 0x00, 0x00, 0x00])
            var.set([])

class TestGetLogValues(TestCase):
    @mock.patch("pylibftdi.Device")
    def setUp(self, device):
        self.ecu = me7.ECU()

    @mock.patch("me7.ECU.getlogrecord")
    def test_getlogvalues(self, getlogrecord):
        self.ecu._logged_variables.append(me7.Variable("foo", 0x00))
        getlogrecord.return_value = [0x00, 0x00, 0x01, 0x00]
        variables = self.ecu.getLogValues()
        self.assertEqual(variables['foo'].get(), 1)
 
