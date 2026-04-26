from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from . import local_inventory_query
from . import order_selection
from . import payment_completion
from . import peer_payment_completion
from . import peer_inventory_query
from . import peer_stock_inbound
from . import peer_stock_outbound
from . import stock_inbound
from . import stock_outbound
from .constants.prefixes import (
    INVENTORY_LOOKUP_LOCAL_PREFIX,
    INVENTORY_LOOKUP_PEERS_PREFIX,
    LOCAL_STOCK_INBOUND_PREFIX,
    LOCAL_STOCK_OUTBOUND_PREFIX,
    PEER_STOCK_INBOUND_PREFIX,
    PEER_STOCK_OUTBOUND_PREFIX,
)
from .domain.inventory_lookup_local.skill import SKILL_METADATA as INVENTORY_LOCAL_META
from .domain.inventory_lookup_peers.skill import SKILL_METADATA as INVENTORY_PEERS_META
from .domain.local_stock_inbound.skill import SKILL_METADATA as STOCK_INBOUND_META
from .domain.order_selection.skill import SKILL_METADATA as ORDER_SELECTION_META
from .domain.local_stock_outbound.skill import SKILL_METADATA as STOCK_OUTBOUND_META
from .domain.payment_completion.skill import SKILL_METADATA as PAYMENT_COMPLETION_META
from .domain.peer_payment_completion.skill import SKILL_METADATA as PEER_PAYMENT_COMPLETION_META
from .domain.peer_stock_inbound.skill import SKILL_METADATA as PEER_INBOUND_META
from .domain.peer_stock_outbound.skill import SKILL_METADATA as PEER_OUTBOUND_META

if TYPE_CHECKING:
    from .agent import PartsMultiAgent


@dataclass(frozen=True)
class Command:
    parser: Callable[[str], Any]
    handler: Callable[['PartsMultiAgent', Any], Awaitable[Any]]


@dataclass(frozen=True)
class Skill:
    metadata: Any
    parser: Callable[[str|dict], Any]
    handler: Callable[['PartsMultiAgent', Any], Awaitable[Any]]


SKILLS: dict[str, Skill] = {
    INVENTORY_LOCAL_META.skill_id: Skill(
        metadata=INVENTORY_LOCAL_META,
        parser=local_inventory_query.parse,
        handler=local_inventory_query.handle,
    ),  # 재고조회
    INVENTORY_PEERS_META.skill_id: Skill(
        metadata=INVENTORY_PEERS_META,
        parser=peer_inventory_query.parse,
        handler=peer_inventory_query.handle,
    ),  # 전국재고조회
    STOCK_INBOUND_META.skill_id: Skill(
        metadata=STOCK_INBOUND_META,
        parser=stock_inbound.parse,
        handler=stock_inbound.handle,
    ),  # 주문하기
    ORDER_SELECTION_META.skill_id: Skill(
        metadata=ORDER_SELECTION_META,
        parser=order_selection.parse,
        handler=order_selection.handle,
    ),  # 주문선택
    PAYMENT_COMPLETION_META.skill_id: Skill(
        metadata=PAYMENT_COMPLETION_META,
        parser=payment_completion.parse,
        handler=payment_completion.handle,
    ),  # 결제완료
    PEER_PAYMENT_COMPLETION_META.skill_id: Skill(
        metadata=PEER_PAYMENT_COMPLETION_META,
        parser=peer_payment_completion.parse,
        handler=peer_payment_completion.handle,
    ),  # 피어결제완료
    STOCK_OUTBOUND_META.skill_id: Skill(
        metadata=STOCK_OUTBOUND_META,
        parser=stock_outbound.parse,
        handler=stock_outbound.handle,
    ),  # 출고하기
    PEER_INBOUND_META.skill_id: Skill(
        metadata=PEER_INBOUND_META,
        parser=peer_stock_inbound.parse,
        handler=peer_stock_inbound.handle,
    ),  # 피어입고요청하기
    PEER_OUTBOUND_META.skill_id: Skill(
        metadata=PEER_OUTBOUND_META,
        parser=peer_stock_outbound.parse,
        handler=peer_stock_outbound.handle,
    ),  # 피어출고요청하기
}

# 호환성을 위해 기존 COMMANDS도 제공 (Skill을 Command로 변환)
COMMANDS: dict[str, Command] = {
    skill_id: Command(parser=skill.parser, handler=skill.handler)
    for skill_id, skill in SKILLS.items()
}
