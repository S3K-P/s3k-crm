"""Shared Platform layer (ADR-003).

Owns identity, organizations, authorization, documents, audit and
notifications — capabilities every S3K product consumes.

Boundary rule: **Platform must never import from ``app.products``.** Products
consume Platform capabilities through the service interfaces exported by these
packages. See ARCHITECTURE-BOUNDARIES.md.
"""
