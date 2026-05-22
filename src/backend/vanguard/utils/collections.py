"""Small collection normalization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar


T = TypeVar("T")


def unique_preserving_order(values: Iterable[T]) -> list[T]:
    """Return unique values while preserving first-seen order."""

    return list(dict.fromkeys(values))


def clean_strings(values: Iterable[str]) -> list[str]:
    """Strip strings and drop empty values."""

    return [value.strip() for value in values if value and value.strip()]
