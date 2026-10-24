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

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        load_dotenv(override=False)

        raw_api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_key: str = raw_api_key.strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing in .env")

        timeout_env = os.getenv("OPENAI_REQUEST_TIMEOUT", "30")
        try:
            parsed_timeout: int = (
                timeout if timeout is not None else int(timeout_env)
            )
            self.timeout: int = max(1, parsed_timeout)
        except ValueError:
            self.timeout = 30

        self.model: str = (model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()

        raw_base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.base_url: Optional[str] = raw_base_url.strip() if raw_base_url else None

        retries_env = os.getenv("OPENAI_MAX_RETRIES", "3")
        try:
            parsed_retries: int = (
                max_retries if max_retries is not None else int(retries_env)
            )
            self.max_retries: int = max(1, parsed_retries)
        except ValueError:
            self.max_retries = 3
