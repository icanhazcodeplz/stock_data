import unittest

from alpaca.trading.enums import AssetExchange

from stock_data.get_all_stock_names import get_all_stock_names


class GetAllStockNamesTest(unittest.TestCase):
    def test_three_from_nasdaq_and_amex(self):
        names = get_all_stock_names(
            exchanges=(AssetExchange.NASDAQ, AssetExchange.AMEX),
            limit_per_exchange=3,
        )

        self.assertEqual(len(names), 6)
        for symbol in names:
            self.assertIsInstance(symbol, str)
            self.assertTrue(symbol)
        print()


if __name__ == "__main__":
    unittest.main()
