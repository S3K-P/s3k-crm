"""Combining duplicate records into one, without losing anything.

Duplicates are the CRM's most common data problem and merging them is its most
dangerous operation: it is the one place the product deliberately makes two
records into one, and a mistake is not visible until somebody looks for
history that is no longer there. Everything in this module exists to make that
impossible — see :mod:`.service`.
"""
