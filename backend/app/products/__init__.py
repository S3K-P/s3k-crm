"""Product layer (ADR-004).

Each product owns its own business entities. Products may import Platform
service interfaces; Platform may never import a product. Products must not
import one another directly — cross-product interaction goes through Platform
services or domain events (ADR-013).
"""
