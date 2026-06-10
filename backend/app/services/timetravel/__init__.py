"""Time-travel run debugger.

Records every agent run as an append-only event log (model calls, tool calls,
state mutations, step boundaries), then offers:

* deterministic **replay** of any past run from its log with zero model/tool
  calls;
* **edit-and-fork** — rewind to step N, change the prompt or a tool/step result,
  and re-run forward while serving the unchanged prefix from a step-keyed cache
  so those steps are never re-billed.
"""

from app.services.timetravel.cache import CacheMiss, ResponseCache
from app.services.timetravel.fork import ForkService, fork_service
from app.services.timetravel.recorder import NullRecorder, RunRecorder
from app.services.timetravel.replayer import (
    build_timeline,
    load_events,
    reconstruct_agent_config,
    replay_with_executor,
)

__all__ = [
    "CacheMiss",
    "ForkService",
    "NullRecorder",
    "ResponseCache",
    "RunRecorder",
    "build_timeline",
    "fork_service",
    "load_events",
    "reconstruct_agent_config",
    "replay_with_executor",
]
