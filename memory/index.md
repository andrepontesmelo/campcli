---
type: index
title: campcli memory
description: OKF knowledge bundle — durable, git-tracked project knowledge shared by all agents (Claude Code + opencode).
---

# campcli memory

[OKF](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle: one markdown concept per file, each with a `type` in YAML frontmatter,
cross-linked by relative links. The shared system of record for durable project
knowledge (decisions, facts, constraints, gotchas). Git-tracked.

## How to use
- One concept per file. Filename (minus `.md`) is its stable ID.
- Required frontmatter: `type`. Optional: `title, description, resource, tags, timestamp`.
- Cross-link with relative markdown links. Update this index when adding a concept;
  append notable changes to [the log](log.md).

## Concepts
- [daily-availability-grid](daily-availability-grid.md) — `/api/availability/map`
  daily slots are positional and date-less; slice by index from the fetch start.
