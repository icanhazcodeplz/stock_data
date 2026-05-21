from dataclasses import dataclass

import yfinance as yf


@dataclass
class Financials:
    symbol: str
    float_shares: int | None
    short_ratio: float | None
    short_interest: int | None
    sector: str | None
    industry: str | None
    country: str | None
    exchange: str | None
    short_float: float | None


def get_financials(symbol: str) -> Financials:
    info = yf.Ticker(symbol).info
    return Financials(
        symbol=symbol,
        float_shares=info.get("floatShares"),
        short_ratio=info.get("shortRatio"),
        short_interest=info.get("sharesShort"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        country=info.get("country"),
        exchange=info.get("exchange"),
        short_float=info.get("shortPercentOfFloat"),
    )
