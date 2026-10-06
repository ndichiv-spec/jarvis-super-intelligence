# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the Jarvis project.

## What is an ADR?

An Architecture Decision Record is a short document that captures an important architectural decision made along with its context and consequences.

## ADR Index

| ADR # | Title | Status | Date |
|-------|-------|--------|------|
| 0001 | [Use FastAPI as the Core API Framework](0001-use-fastapi-as-api-framework.md) | Accepted | 2024-01-15 |
| 0002 | [Use pytest with pytest-asyncio for Testing](0002-use-pytest-with-pytest-asyncio-for-testing.md) | Accepted | 2024-01-15 |
| 0003 | [Use Structured JSON Logging with Contextvars](0003-use-structured-json-logging-with-contextvars.md) | Accepted | 2024-02-01 |
| 0004 | [Use Module-Level Singletons for Infrastructure](0004-use-module-level-singletons-for-infrastructure.md) | Accepted | 2024-02-15 |

## Process

1. When a significant architectural decision is made, create a new ADR
2. Copy `TEMPLATE.md` and name it `NNNN-title-with-dashes.md`
3. Fill in the sections
4. Set status to "Proposed", "Accepted", "Deprecated", or "Superseded"
5. Add to the index
6. Submit as part of the PR that implements the decision
