"""No tables of its own.

A merge writes to tables other modules own, and records what it did in the
audit trail those modules already write to. The one piece of *storage* it
needed — a ``merged_into_id`` pointer on the losing record, so a bookmark or an
integration holding the old id can still be resolved — belongs on the record it
describes and is declared in that module's ``models.py``.

This file exists so the module keeps the seven-file shape every other module
has (ARCHITECTURE-BOUNDARIES.md), and so the absence of a table is a stated
decision rather than something a reader has to infer.
"""
