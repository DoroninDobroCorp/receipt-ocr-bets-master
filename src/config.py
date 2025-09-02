"""
Config module
-------------
Provides configuration loader for environment variables.
"""

from __future__ import annotations
import os
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Configuration loader for environment variables."""

    def __init__(self) -> None:
        load_dotenv()
        self.api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        self.timeout: int = int(os.getenv("OPENAI_REQUEST_TIMEOUT", "30"))
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing in .env")
