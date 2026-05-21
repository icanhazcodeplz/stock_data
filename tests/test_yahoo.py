import unittest

from stock_data.clients.yahoo import get_financials


class YahooFinancialsTest(unittest.TestCase):
    def test_aapl_and_mwc(self):
        for symbol in ("AAPL", "MWC"):
            with self.subTest(symbol=symbol):
                f = get_financials(symbol)
                print(f)
                self.assertEqual(f.symbol, symbol)
                self.assertIsInstance(f.float_shares, int)
                self.assertIsInstance(f.sector, str)
                self.assertIsInstance(f.industry, str)
                if f.short_ratio is not None:
                    self.assertIsInstance(f.short_ratio, float)
                if f.short_interest is not None:
                    self.assertIsInstance(f.short_interest, int)


if __name__ == "__main__":
    unittest.main()
