# Agents

Agents are the only parts of the system that call Claude. They produce **structured data**: never geometry, coordinates or code.

| Agent | Phase | Input | Output |
| --- | --- | --- | --- |
| Architect Agent | 3 | Plain-English brief plus optional advanced options | `DesignIntent` |
| Modification Agent | 11 | Current design plus a plain-English change request | `ChangeSet` |

## Architect Agent

`backend/app/agents/architect_agent.py`, system prompt in `backend/app/agents/prompts/architect_system.md`.

### What it decides, and what it doesn't

Claude decides **what the building needs**: rooms with target areas and window amounts, which rooms connect (door or open-plan), where each stair starts and arrives, the footprint, the roof and the materials. It also lists the assumptions it made where the brief was silent.

It does **not** place rooms. Language models are good at interpreting requirements and poor at producing non-overlapping coordinates, so positions come from the deterministic planner (Phase 4), and the result is checked again by the specification validator.

### How the call works

```
brief + advanced options
        │
        ▼
Claude (structured output: DesignIntent JSON schema)
        │  JSON text
        ▼
Pydantic validation ── every original constraint (ranges, ID patterns, enum values)
        │
        ▼
Apply directly-settable options (style, building type, footprint, roof type)
        │
        ▼
Deterministic intent checks ── rooms reachable, stairs valid, areas fit the footprint,
        │                      required counts (bedrooms, bathrooms, garage, floors) met
        ▼
errors? ──yes──► send the problems back, ask for the complete corrected design (once by default)
        │                 still failing ──► 422 "Claude returned an invalid room layout" + issues
        no
        ▼
InterpretationResult (intent, warnings, options applied, attempts, token usage)
```

### Why structured outputs rather than forced tool use

The first design forced a tool call (`tool_choice: {"type": "tool"}`). Current Anthropic documentation states that forced tool use returns a 400 error on Claude Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1, and recommends [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) when a response must have a fixed JSON shape. The agent therefore sends the `DesignIntent` schema in `output_config.format`, which constrains decoding to that schema on every supported model.

Structured outputs impose limits that shaped the model:

- **At most 24 optional and 16 union-typed fields** across the schema. Every `DesignIntent` field is required; the only nullable field is the accent material. A test enforces the limits.
- **No numeric ranges, length limits or regex patterns** in the schema sent to the API. `anthropic.transform_schema()` moves them into field descriptions, and Pydantic enforces the originals on the response.
- **Enum capitalisation is not guaranteed**, so enum values are lower-cased before validation.
- A reply can still end with `stop_reason` `refusal` or `max_tokens`. Both are handled explicitly and never retried blindly.

### Advanced options

Options the user sets in the UI are passed to Claude inside `<constraints>` as requirements, then enforced in code:

- **Set directly** after the reply, with a note shown to the user: building type, style, footprint width and depth, roof type (with a sensible pitch).
- **Checked**, because they cannot be changed without redesigning: floors, bedrooms, bathrooms (including en-suites), garage size and approximate height. A mismatch is an error, which triggers the corrective attempt with the requirement restated.

### Untrusted input

The brief is user text. It is placed inside `<building_request>` tags, and any occurrence of the agent's own tag names is removed so the brief cannot close its tags or inject fake constraints. The system prompt tells Claude to treat the brief purely as a building description. More importantly, nothing Claude returns is executed: it is parsed into typed data and validated.

### Cost and latency

The system prompt is marked for prompt caching, so the corrective attempt and later briefs reuse it. The first request with a new schema also compiles a grammar, which adds latency; compiled grammars are cached by the API for 24 hours. Token usage is returned with every interpretation and logged.

## Testing agents

| Suite | What it covers | Needs a key |
| --- | --- | --- |
| `tests/test_architect_agent.py` | The full retry loop with a scripted client: corrections, invalid JSON, schema violations, refusals, truncation, non-building briefs, constraints, prompt-injection tags | No |
| `tests/test_intent_validation.py` | Every intent rule | No |
| `tests/test_claude_service.py` | The real Anthropic SDK against a mocked HTTP transport: request shape, response parsing, error mapping | No |
| `tests/live/test_architect_live.py` | All five example prompts, constraint overrides and a non-building brief against the real API | Yes |

Run the live suite (costs a few cents):

```bash
cd backend
RUN_LIVE_CLAUDE_TESTS=1 python -m pytest -m live -v -s
```

Try a single brief from the terminal:

```bash
python -m scripts.interpret_brief "A modern three-bedroom bungalow with a flat roof"
python -m scripts.interpret_brief --example luxury-house --bedrooms 5
```

## Modification Agent

`backend/app/agents/modification_agent.py`, system prompt in `backend/app/agents/prompts/modification_system.md`, deterministic parts in `backend/app/modification/`.

### A design is intent plus overrides

Some changes alter the layout ("make the living room 1 m wider") and some do not ("add a window to the master bedroom"). If every change edited the specification directly, a later layout change would re-plan the house and silently lose the earlier window. A design therefore has two layers:

| Layer | Holds | Operations |
| --- | --- | --- |
| Design intent | rooms, sizes, sides, roof, balconies | `set_room_area`, `set_room_width`, `add_room`, `remove_room`, `rename_room`, `set_room_side`, `set_room_glazing`, `set_roof`, `add_balcony`, `remove_balcony` |
| Overrides | an ordered list of finishing changes addressed by ID | `set_exterior_material`, `set_room_finish`, `add_window`, `remove_window` |

The current specification is always: plan the intent, then apply the overrides in order. Overrides survive later re-plans; one that no longer applies (its room was removed) is dropped with a note.

### Keeping the rest of the house where it was

Re-planning from scratch after a small change would rearrange the house, because the layout search balances every room. Instead the previous arrangement is read back from the current specification (`app/planner/anchor.py`): where the hall runs, whether the stair is central, and each room's side and front-to-rear position. The planner keeps that arrangement and only searches again if the change cannot fit, in which case it says so.

- **Width** is across the house, and a room spans its side of the hall, so making it wider moves the hall. The space comes from the other side if those rooms stay at least 3 m wide; otherwise the building is extended by the difference.
- **Moving a room to the other side** swaps it with the most similar-sized room there; both keep their front-to-rear positions.

### Every change is checked, twice

1. Each operation is parsed into a strictly typed model (`app/modification/changeset.py`) and checked against the design: IDs must exist, materials must suit the surface, the entrance and stair rooms cannot be removed, balconies need an upper floor.
2. After re-planning, the result is validated and **each operation's effect is verified**: a room asked to be wider must be that wide, a moved room must be on its new side, an added balcony must exist. A change that would silently not happen is an error instead.

Problems go back to Claude once with specific, actionable messages, for example "Living Room could not be made larger by area: the rooms beside it fix its depth. Use set_room_width to change it across the house instead." If they persist, the request fails with the reasons and the design is unchanged.

### What the user sees

The response lists what actually changed, computed by comparing the specifications before and after (`app/modification/diff.py`), for example "Living Room: 14.3 m² -> 17.9 m² (5.10 x 3.50 m)" or "Added a 1.2 m window to Master Bedroom (left wall)". Claude's own summary and assumptions are shown alongside.

### Blender

A modified design is rebuilt in full. Builds take under a second, and object names are deterministic, so every unchanged wall, room and window keeps its name and only the changed parts differ; a test checks this.

### Testing

| Suite | What it covers | Needs a key |
| --- | --- | --- |
| `tests/test_modification.py` | The brief's example changes applied deterministically, overrides surviving re-plans, invalid operations, a rebuild keeping unchanged objects | No |
| `tests/test_modification_agent.py` | The full loop with a scripted Claude: the definition-of-done change, corrections, a blocked change with a useful hint, safe failure, the endpoint | No |
| `tests/live/test_modification_live.py` | The brief's seven example requests against the real API | Yes |
