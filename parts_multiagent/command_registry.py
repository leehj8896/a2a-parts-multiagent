from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import local_inventory_query
from . import peer_inventory_query
from . import peer_stock_inbound
from . import peer_stock_outbound
from . import stock_inbound
from . import stock_outbound
from .constants.prefixes import (
    LOCAL_AGENT_PREFIX,
    LOCAL_STOCK_INBOUND_PREFIX,
    LOCAL_STOCK_OUTBOUND_PREFIX,
    PEER_AGENTS_PREFIX,
    PEER_STOCK_INBOUND_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)

if TYPE_CHECKING:
    from .agent import PartsMultiAgent


@dataclass(frozen=True)
class Command:
    parser: Callable[[str], Any]
    handler: Callable[['PartsMultiAgent', Any], Awaitable[Any]]


COMMANDS: dict[str, Command] = {
    LOCAL_AGENT_PREFIX: Command(
        parser=local_inventory_query.parse,
        handler=local_inventory_query.handle,
    ),
    PEER_AGENTS_PREFIX: Command(
        parser=peer_inventory_query.parse,
        handler=peer_inventory_query.handle,
    ),
    LOCAL_STOCK_INBOUND_PREFIX: Command(
        parser=stock_inbound.parse,
        handler=stock_inbound.handle,
    ),
    LOCAL_STOCK_OUTBOUND_PREFIX: Command(
        parser=stock_outbound.parse,
        handler=stock_outbound.handle,
    ),
    PEER_STOCK_INBOUND_PREFIX: Command(
        parser=peer_stock_inbound.parse,
        handler=peer_stock_inbound.handle,
    ),
    PEER_STOCK_OUTBOUND_PREFIX: Command(
        parser=peer_stock_outbound.parse,
        handler=peer_stock_outbound.handle,
    ),
}
