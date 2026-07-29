import pytest

from stock_data.clients.yahoo import get_financials

pytestmark = pytest.mark.network


@pytest.mark.parametrize("symbol", ["AAPL", "MWC"])
def test_financials(symbol):
    f = get_financials(symbol)
    assert f.symbol == symbol
    assert isinstance(f.float_shares, int)
    assert isinstance(f.sector, str)
    assert isinstance(f.industry, str)
    if f.short_ratio is not None:
        assert isinstance(f.short_ratio, float)
    if f.short_interest is not None:
        assert isinstance(f.short_interest, int)
