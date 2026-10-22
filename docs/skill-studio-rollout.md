# Skill Studio Rollout

## Goal

This project is migrating from legacy `domain / knowledge / sql_rule` routing toward a datasource-centered Skill Studio architecture built on:

- `datasource_profiles`
- `skill_packs`
- `skill_documents`

The migration has now crossed the retirement boundary: the chat workbench runs on the autonomous datasource agent only, and the old `domain / knowledge / sql_rule` surfaces are being removed from this branch.

## Current Runtime Policy

The chat workflow now uses one runtime path per datasource:

1. Every question enters the datasource-scoped autonomous agent runtime.
2. If the selected datasource has no usable skill packs yet, the system returns an explicit onboarding guidance message instead of falling back to legacy routing.
3. Clarification interrupts remain supported in the main runtime.
4. Runtime-learned skill packs (`origin=runtime-learning`, `status=draft`) do not participate in SQL generation until manually approved.
5. Datasource memories are merged directly into the agent-maintained datasource memory document when confidence is high.
6. Datasource/global runtime rules are now persisted in `datasource_profiles.profile_json.runtime_rules`, while pack-local rules stay on `skill_pack.business_rules`.

## Datasource Learning Loop

Alembic revision `0009` originally added the Hermes-inspired learning primitives:

- `thread_context_summaries`
- `thread_conversation_turns`

The retired `datasource_memory_entries` table is removed by revision `0018`; `learning_review_items`, `skill_activation_logs`, the initial `foundation_meta` placeholder, and old local demo tables are removed by revision `0019`.

The runtime now:

1. records raw turns per `datasource_id + thread_id`
2. loads datasource-scoped memory before skill selection
3. compresses older turns into a rolling structured summary when the thread gets long
4. runs a post-turn reviewer that writes stable memory and QA examples directly
5. surfaces the results in the new `Admin / Skills` interface

## Migration Mapping

Legacy assets were initially mapped into the new model by Alembic revision `0008`:

- `datasources` + `datasource_schema_snapshots` -> `datasource_profiles`
- `business_domains` -> initial `skill_packs`
- `knowledge_chunks` -> `skill_documents`
- domain-scoped `sql_rules` -> `skill_documents` plus `skill_pack.business_rules`
- datasource/global `sql_rules` -> datasource-scoped runtime rules stored in `datasource_profiles.profile_json`

Alembic revision `0010` finishes the retirement by:

- syncing the remaining legacy knowledge/rule payloads into `skill_documents` and datasource profile runtime rules
- dropping `legacy_domain_id` from `skill_packs`
- removing `business_domains`, `domain_schema_context`, `knowledge_collections`, `knowledge_chunks`, and `sql_rules`

## Skill Studio Backend Surface

The backend now exposes datasource-centered APIs for:

- running datasource onboarding
- reading datasource profiles
- listing and editing skill packs
- listing and editing datasource memory
- listing thread-summary compression diagnostics
- listing, creating, updating, and deleting skill documents
- observing runtime-learned QA examples and memory updates

Legacy admin routes are no longer part of the active backend surface on this branch.

## Verification Matrix

The following checks are passing against the current codebase:

- `cd backend && uv run pytest tests/api/test_chat_stream.py tests/api/test_admin_datasources.py tests/api/test_admin_skill_packs.py tests/api/test_admin_learning.py tests/services/test_thread_context.py tests/services/test_learning_review.py`
- `cd web && npm run lint && npm run build`

The backend tests cover:

- autonomous-agent clarification/resume flow
- autonomous-agent guidance when a datasource has no ready skill packs
- datasource memory injection and rolling thread compression
- datasource onboarding persistence
- skill-pack document management
- autonomous-agent retrieval, SQL generation handoff, and learning review policies

## Recommended Switch Order

1. Import or create the datasource in `Admin / Datasources`.
2. Run datasource introspection and onboarding.
3. Review generated skill packs and supporting documents.
4. Use `Admin / Skills` to adjust the canonical skill document only when an admin intentionally curates an asset.
5. Use the main workbench so runtime learning can produce memory and QA examples from successful turns.
6. Once the skill packs look stable, use that datasource directly in the main workbench.

## Remaining Follow-Up

- Add explicit re-embedding controls for manually edited skill documents.
- Add richer evaluation around memory precision / recall once more real datasource traces are available.
