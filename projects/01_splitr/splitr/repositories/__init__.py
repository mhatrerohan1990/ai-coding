"""Data access: every SQL statement lives here and returns model objects.

Repositories never commit. The service that calls them decides the transaction
boundary (see ``db.transaction``), so several repository calls can be atomic.
"""
