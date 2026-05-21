from alpaca.trading.enums import AssetExchange

from stock_data.get_all_stock_names import get_all_stock_names


def test_three_from_nasdaq_and_amex():
    names = get_all_stock_names(
        exchanges=(AssetExchange.NASDAQ, AssetExchange.AMEX),
        limit_per_exchange=3,
    )

    assert len(names) == 6
    for symbol in names:
        assert isinstance(symbol, str)
        assert symbol
