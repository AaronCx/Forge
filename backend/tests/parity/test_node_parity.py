"""Parity golden tests: freeze every node type's output dict.

Executes all 44 registered node types with fixed inputs against fakes and
snapshots each output to ``golden/node_<key>.json``. A drift here means a
harness-transformation phase changed a node's observable output — intended
changes are re-baselined with ``FORGE_UPDATE_GOLDEN=1``.
"""

from __future__ import annotations

import pytest

from app.services.blueprint_nodes.registry import NODE_REGISTRY

from ._harness import assert_golden
from ._nodes import NODE_FIXTURES, run_node

ALL_NODE_KEYS = sorted(NODE_REGISTRY.keys())


def test_registry_has_expected_node_count():
    # Ground truth was 44 (the plan's "48" counted 4 phantom workspace nodes);
    # Phase 9 added subagent_run as registry entry 45.
    assert len(NODE_REGISTRY) == 45


def test_every_node_has_a_parity_fixture():
    missing = set(NODE_REGISTRY) - set(NODE_FIXTURES)
    assert not missing, f"node types without a parity fixture: {sorted(missing)}"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ALL_NODE_KEYS)
async def test_node_output_matches_golden(key: str):
    output = await run_node(key)
    assert_golden(f"node_{key}", output)
