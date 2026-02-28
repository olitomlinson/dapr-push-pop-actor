"""
Main entry point for Locust load tests.
Imports all scenarios to make them available in web UI dropdown.

When starting Locust, it will automatically detect all HttpUser subclasses
defined in this file or imported here, and make them available for selection
in the web UI.
"""

# Import scenarios as they are implemented
# Uncomment these imports as scenario files are created
# from scenarios.s1_push_only import PushOnlyUser
# from scenarios.s2_pop_only import PopOnlyUser
from scenarios.s3_mixed import MixedWorkloadUser
# from scenarios.s4_concurrent import ConcurrentQueueUser
# from scenarios.s5_queue_size import QueueSizeUser
# from scenarios.s6_burst import BurstTrafficUser
# from scenarios.s7_failure import FailureScenarioUser

# All user classes are automatically detected by Locust
# and appear in the web UI dropdown when multiple are defined

__all__ = [
    "MixedWorkloadUser",
    # Add other user classes here as they are implemented
]
