"""Cross-cutting infrastructure: config, database, redis, logging, exceptions.

``app.core`` is the only package both the Shared Platform and product modules
may depend on. It must never import from ``app.platform`` or ``app.products``.
"""
