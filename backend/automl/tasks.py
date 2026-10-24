"""Shared type definitions for the AutoML engine."""

from typing import Literal, get_args

Task = Literal["classification", "regression"]
TASKS: tuple[str, ...] = get_args(Task)
