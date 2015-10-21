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
        self.ecu.bbang([test_value])

        port_values = [call[0][0] for call in bbd_port.call_args_list]
        sleep_values = [call[0][0] for call in sleep.call_args_list]

        # Starts with high, then low, and ends high.
        self.assertEqual(port_values[0], 1)
        self.assertEqual(port_values[1], 0)
        self.assertEqual(port_values[-1], 1)

        value_bits = port_values[2:-1]
        reconstructed_value = int("0b" + "".join(map(lambda b: str(b), value_bits)), 2)
        # Invert reconstructed value, we're supposed to transmit the inverse.
        reconstructed_value ^= 0xff
        self.assertEqual(test_value, reconstructed_value)

        # Check the bit timings. Half second to start, 0.2s between each bit.
        self.assertEqual(sleep_values[0], 0.5)
        for value in sleep_values[2:]:
            self.assertEqual(value, 0.2)

        bbd_open.assert_called_with() # called twice
        bbd_close.assert_called_once_with()
        bbd_direction.assert_called_with(1)
 
