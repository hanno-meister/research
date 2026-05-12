"""Vanguard package.

This package can be imported as either ``vanguard`` when ``src`` is on
``PYTHONPATH`` or ``src.vanguard`` in repo-root smoke tests.
"""

from __future__ import annotations

import sys


sys.modules.setdefault("vanguard", sys.modules[__name__])
