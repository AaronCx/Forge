"""Eval-driven self-optimization loop.

Closes the loop between the eval framework and agent configs: an eval run
completes, an optimizer reads the failures, proposes N prompt variants, runs the
eval suite against each, promotes the winner behind an approval gate, and logs
the lineage.
"""

from app.services.optimizer.service import OptimizerService, optimizer_service
from app.services.optimizer.variant_generator import (
    LLMVariantGenerator,
    PromptVariant,
    VariantGenerator,
    default_variant_generator,
)

__all__ = [
    "LLMVariantGenerator",
    "OptimizerService",
    "PromptVariant",
    "VariantGenerator",
    "default_variant_generator",
    "optimizer_service",
]
