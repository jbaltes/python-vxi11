import unittest
from vxi11.vxi11 import parse_visa_resource_string

class TestVxi11(unittest.TestCase):

    def test_parse_visa_resource_string(self):
        f = parse_visa_resource_string

        # TCPIP INSTR Tests
        self.assertEqual(f('TCPIP::10.0.0.1::INSTR')['prefix'], 'TCPIP')
        self.assertEqual(f('TCPIP::10.0.0.1::INSTR')['type'], 'TCPIP')
        self.assertEqual(f('TCPIP::10.0.0.1::INSTR')['arg1'], '10.0.0.1')
        self.assertEqual(f('TCPIP::10.0.0.1::INSTR')['arg2'], None)
        self.assertEqual(f('TCPIP::10.0.0.1::INSTR')['suffix'], 'INSTR')

        self.assertEqual(f('TCPIP0::10.0.0.1::INSTR')['prefix'], 'TCPIP0')
        self.assertEqual(f('TCPIP0::10.0.0.1::INSTR')['type'], 'TCPIP')

        self.assertEqual(f('TCPIP0::10.0.0.1::gpib,5::INSTR')['prefix'], 'TCPIP0')
        self.assertEqual(f('TCPIP0::10.0.0.1::gpib,5::INSTR')['arg2'], 'gpib,5')

        self.assertEqual(f('TCPIP0::10.0.0.1::usb0::INSTR')['prefix'], 'TCPIP0')
        self.assertEqual(f('TCPIP0::10.0.0.1::usb0::INSTR')['arg2'], 'usb0')

        self.assertEqual(f('TCPIP0::10.0.0.1::inst0::INSTR')['prefix'], 'TCPIP0')
        self.assertEqual(f('TCPIP0::10.0.0.1::inst0::INSTR')['arg2'], 'inst0')

        self.assertEqual(f('TCPIP0::10.0.0.1::hislip0::INSTR')['prefix'], 'TCPIP0')
        self.assertEqual(f('TCPIP0::10.0.0.1::hislip0::INSTR')['arg2'], 'hislip0')

if __name__ == '__main__':
    unittest.main()
