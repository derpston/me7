from unittest import TestCase
import mock
import me7


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
    def test_commandValidate(self, checksum, validate):
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

