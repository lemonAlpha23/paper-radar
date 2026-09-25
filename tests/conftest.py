import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--send-telegram",
        action="store_true",
        default=False,
        help="Send a real test message to TELEGRAM_CHAT_ID using credentials from .env",
    )
