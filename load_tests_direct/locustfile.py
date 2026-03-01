"""
Main entry point for Locust direct actor load tests.
Imports all scenarios to make them available in web UI dropdown.

When starting Locust, it will automatically detect all User subclasses
defined in this file or imported here, and make them available for selection
in the web UI.
"""

# Import all direct actor scenarios
from scenarios.s3_mixed_dapr import (
    MixedWorkloadDaprUser,
    ProducerHeavyDaprUser,
    ConsumerHeavyDaprUser,
    MultiPriorityMixedDaprUser,
    BalancedLargeItemsDaprUser
)

# All user classes are automatically detected by Locust
# and appear in the web UI dropdown when multiple are defined

__all__ = [
    "MixedWorkloadDaprUser",
    "ProducerHeavyDaprUser",
    "ConsumerHeavyDaprUser",
    "MultiPriorityMixedDaprUser",
    "BalancedLargeItemsDaprUser",
]
