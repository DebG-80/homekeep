"""Runtime publication overlay: `CATALOG / STATUS#{item}` (TDD §4.7, §6.1; AT-24).

An admin can withdraw a catalog item (all its versions) without a redeploy. The file status
applies unless the overlay says otherwise.
"""

from __future__ import annotations

from app.catalog.loader import CatalogItem
from app.store.table import Table

OVERLAY_PK = "CATALOG"


def effective_status(table: Table, item: CatalogItem) -> str:
    override = table.get(OVERLAY_PK, f"STATUS#{item.item_id}")
    return override["status"] if override else item.status
