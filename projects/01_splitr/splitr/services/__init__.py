"""Business rules: validation, orchestration and transaction boundaries.

Services know nothing about HTTP (no Flask) and contain no SQL; they use the
repositories for data and ``db.transaction`` to make multi-step writes atomic.
"""
