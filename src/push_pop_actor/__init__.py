"""
Dapr Push-Pop Actor - A simple queue-based actor for Dapr applications.

This library provides a reusable Dapr actor that implements a FIFO queue
for storing and retrieving dictionaries. Perfect for lightweight message
queuing, task scheduling, or any scenario requiring ordered processing.
"""

from .actor import PushPopActor, PushPopActorInterface

__version__ = "0.1.0"
__all__ = ["PushPopActor", "PushPopActorInterface"]
