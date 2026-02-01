"""
jike — Jike social network client for humans and AI agents.

Author: Claude Opus 4.5
"""

from .auth import authenticate, refresh_tokens
from .client import JikeClient
from .types import TokenPair

__all__ = ["JikeClient", "TokenPair", "authenticate", "refresh_tokens"]
__version__ = "0.1.0"
