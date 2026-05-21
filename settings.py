import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.absolute()


class ENV:
    ALPACA_KEY = os.environ["ALPACA_KEY"]
    ALPACA_SECRET = os.environ["ALPACA_SECRET"]
    ALPACA_PAPER_KEY = os.environ["ALPACA_PAPER_KEY"]
    ALPACA_PAPER_SECRET = os.environ["ALPACA_PAPER_SECRET"]
