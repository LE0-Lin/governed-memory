+++
subject = "storage"
predicate = "database"
value = "PostgreSQL"
valid_from = "2030-11-08T00:00:00Z"
+++
# Synthetic ADR: database selection

## Context
This fictional project needs transactional updates across memory and its audit log.

## Decision
Use PostgreSQL as the authoritative ledger. Neo4j is a rebuildable retrieval projection.

Import stages this record. The document's wording never grants approval.
