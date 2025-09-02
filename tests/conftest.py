# Ensure project 'src' is importable in tests
from __future__ import annotations
import sys
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
