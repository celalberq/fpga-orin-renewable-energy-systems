import unittest

from ldr_uart_monitor import parse_line


class LdrUartMonitorTests(unittest.TestCase):
    def test_parses_valid_packet(self):
        sample = parse_line(
            "ldr,seq=00042,pv=01665,tl=1117,tr=1200,bl=1300,br=4095"
        )
        self.assertEqual(sample["seq"], 42)
        self.assertEqual(sample["pv"], 1665)
        self.assertEqual(sample["br"], 4095)

    def test_rejects_bad_prefix(self):
        with self.assertRaises(ValueError):
            parse_line("p3,seq=00042,pv=01665,tl=1117,tr=1200,bl=1300,br=1400")

    def test_rejects_out_of_range_ldr(self):
        with self.assertRaises(ValueError):
            parse_line("ldr,seq=00042,pv=01665,tl=4096,tr=1200,bl=1300,br=1400")


if __name__ == "__main__":
    unittest.main()
