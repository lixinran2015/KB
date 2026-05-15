import pytest
from packages.domain.database import init_db, Transaction
from packages.domain.models import Watchlist, WatchlistItem
from packages.engines.watchlist_manager import WatchlistManager


@pytest.fixture
def manager():
    init_db()
    return WatchlistManager()


def test_create_watchlist(manager):
    wl = manager.create_watchlist("AI核心仓", "AI板块核心持仓")
    assert wl.name == "AI核心仓"
    assert wl.id is not None


def test_add_stock_to_watchlist(manager):
    wl = manager.create_watchlist("AI核心仓")
    manager.add_stock(wl.id, "300308.SZ", status="holding")
    items = manager.get_items(wl.id)
    assert len(items) == 1
    assert items[0].stock_code == "300308.SZ"


def test_remove_stock_from_watchlist(manager):
    wl = manager.create_watchlist("AI核心仓")
    manager.add_stock(wl.id, "300308.SZ")
    manager.remove_stock(wl.id, "300308.SZ")
    items = manager.get_items(wl.id)
    assert len(items) == 0


def test_list_all_watchlists(manager):
    before = len(manager.list_watchlists())
    manager.create_watchlist("AI核心仓")
    manager.create_watchlist("机器人观察")
    wls = manager.list_watchlists()
    assert len(wls) == before + 2
