import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).parent.absolute()


class _EnvVar:
    """Descriptor that reads its variable from the environment on access.

    Lookup is lazy so importing ``settings`` (e.g. for ``REPO_ROOT``) never
    requires credentials; only code that actually uses a credential needs it
    present in ``.env``.
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, obj: object, objtype: type | None = None) -> str:
        try:
            return os.environ[self._name]
        except KeyError:
            raise RuntimeError(f"Environment variable {self._name} is not set; add it to .env") from None


class ENV:
    ALPACA_KEY = _EnvVar()
    ALPACA_SECRET = _EnvVar()
    ALPACA_PAPER_KEY = _EnvVar()
    ALPACA_PAPER_SECRET = _EnvVar()
