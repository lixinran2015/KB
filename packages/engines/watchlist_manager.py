from typing import List, Optional
from packages.domain.database import get_session
from packages.domain.models import Watchlist, WatchlistItem


class WatchlistManager:
    def create_watchlist(self, name: str, description: str = "") -> Watchlist:
        session = get_session()
        wl = Watchlist(name=name, description=description)
        session.add(wl)
        session.commit()
        session.refresh(wl)
        session.close()
        return wl

    def add_stock(self, watchlist_id: int, stock_code: str, status: str = "watching", notes: str = ""):
        session = get_session()
        item = WatchlistItem(watchlist_id=watchlist_id, stock_code=stock_code, status=status, notes=notes)
        session.add(item)
        session.commit()
        session.close()

    def remove_stock(self, watchlist_id: int, stock_code: str):
        session = get_session()
        item = session.query(WatchlistItem).filter_by(watchlist_id=watchlist_id, stock_code=stock_code).first()
        if item:
            session.delete(item)
            session.commit()
        session.close()

    def get_items(self, watchlist_id: int) -> List[WatchlistItem]:
        session = get_session()
        items = session.query(WatchlistItem).filter_by(watchlist_id=watchlist_id).all()
        session.close()
        return items

    def list_watchlists(self) -> List[Watchlist]:
        session = get_session()
        wls = session.query(Watchlist).all()
        session.close()
        return wls

    def delete_watchlist(self, watchlist_id: int):
        session = get_session()
        wl = session.query(Watchlist).filter_by(id=watchlist_id).first()
        if wl:
            session.delete(wl)
            session.commit()
        session.close()
