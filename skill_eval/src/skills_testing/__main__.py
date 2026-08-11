"""Run the customer-facing skills_testing CLI with `python -m skills_testing`."""

from __future__ import annotations

from .cli.customer_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
