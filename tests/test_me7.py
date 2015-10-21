from unittest import TestCase
import me7

class TestECUExists(TestCase):
    """A pointless test, intended to test the test infrastructure and
    provide an example to build on."""

    def test_ecu_class_exists(self):
        self.assertTrue(getattr(me7, 'ECU'))

