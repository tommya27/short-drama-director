Backend API contract (SQLite core v0.2)

- POST /api/v1/ideas/expand {premise}: offline guided SceneSpec; no model call.
- POST /api/v1/scenes: accepts snake_case SceneSpec or actors alias. Response includes scene_id, scene_spec/spec, top-level spec fields, active_branch_id, branches, state.
- GET/PATCH /scenes/{id}: PATCH may include active_branch_id, branch_id, base_revision; editable fields include characters/actors, items, facts, title, goal, conflict, location, genre, scene_manifest, author_facts, relationships, world, premise. PATCH increments revision and persists.
- GET state/events/facts: branch_id optional. Events/facts can be filtered by actor_id. GET /actors/{actor}/context returns only role-visible facts/events/items and director instructions.
- POST /scenes/{id}/drafts: {branch_id,base_revision,candidate_events?,locks?,request_id?}. Offline generator creates per-role candidates using prior visible events, movement, item pickup/transfer, fact disclosure, and active directives. Draft stays awaiting_approval; formal state unchanged.
- PATCH draft: {version,candidate_events/events,locks,unlock_paths}; locks must be explicit field paths. PATCH clears preview. Preview is required before commit and only current draft version may commit. POST preview returns proposed_state/preview_state and state_diff.
- POST commit: {revision?,idempotency_key?}; requires preview, is idempotent with same key; stale revision 409. POST discard.
- POST /requests/{request_id}/cancel marks cancellation; generation checks cancellation before accepting late result.
- POST branches {from_branch_id, name, base_revision}; branch state/spec fully cloned and isolated.
- POST/DELETE directives; target_actor_id + start_step/end_step are validated and applied only in range.
- POST outputs {type: scene_card|script|storyboard|screenplay, branch_id, source_event_ids/event_ids}; GET scene outputs, GET/PATCH output for editable content and source IDs.
- 409 = revision/lifecycle/lock/idempotency conflicts, 422 = input validation, 404 = missing.

Copied and versioned from baytech2026/workspace/core/narrative: models.py, sandbox.py, service.py, repository.py. Removed legacy scenario conversion and runtime core imports. Added portable agent.py formatter/Agent state, local entity_state.py, offline.py policy and scene_input.py validation. SQLite repository uses DIRECTOR_DB or data/director.db; no runtime imports of baytech2026.

Validation: py -3.13 -m pytest -q backend/tests -> 35 passed (2 third-party deprecation warnings).

SceneSpec save contract update:
- PATCH accepts `scene_id` only if it matches the URL; IDs cannot be changed.
- `goals` is a string array. `locations` maps to authoritative `world.locations`, preserving existing world connections.
- GET scene returns `spec.locations` and `scene_spec.locations` from `world.locations`.
- A scene edit and requested `active_branch_id` are persisted in the same SQLite transaction. 409/422 leaves both unchanged.
- Explicit null is preserved for validation; it no longer silently drops invalid fields.
- Ancient mansion expansion uses `scene_key: mansion`.

Validation (latest): 34 passed, including 22 new API boundaries/atomic edit/cancellation tests. An offline generator is deliberately held during cancellation; its late result is persisted as discarded and cannot commit. No model calls.
