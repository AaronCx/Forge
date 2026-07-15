"""Re-export of kernel message serialization from ``forge-kernel``."""

from forge_kernel.serialize import (
    block_from_dict,
    block_to_dict,
    dataclass_json_schema,
    message_from_dict,
    message_to_dict,
    workflow_spec_from_dict,
    workflow_spec_json_schema,
    workflow_spec_to_dict,
)

__all__ = [
    "block_from_dict",
    "block_to_dict",
    "dataclass_json_schema",
    "message_from_dict",
    "message_to_dict",
    "workflow_spec_from_dict",
    "workflow_spec_json_schema",
    "workflow_spec_to_dict",
]
