from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetExchange, AssetStatus
from alpaca.trading.models import Asset
from alpaca.trading.requests import GetAssetsRequest

from settings import ENV


def trading_client(paper: bool = True) -> TradingClient:
    if paper:
        return TradingClient(ENV.ALPACA_PAPER_KEY, ENV.ALPACA_PAPER_SECRET, paper=True)
    return TradingClient(ENV.ALPACA_KEY, ENV.ALPACA_SECRET, paper=False)


def get_active_us_equities(exchange: AssetExchange, *, paper: bool = True) -> list[Asset]:
    client = trading_client(paper=paper)
    request = GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY,
        status=AssetStatus.ACTIVE,
        exchange=exchange,
    )
    return client.get_all_assets(request)
