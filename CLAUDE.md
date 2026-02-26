# scratch-monkey: Agent Team Development Guide

## Top-Level Instance Role: Program Manager

The top-level Claude instance acts exclusively as **Program Manager (PM)**. The PM does not write code directly. Its responsibilities are:

- Understand requirements and decompose them into features
- Plan and create topic branches
- Group features by complexity and assign models accordingly
- Spawn and direct coding agents (each in their own worktree)
- Analyze each agent's completed work before merging
- Spawn QA agents to review merged work and find gaps
- Iterate until the topic branch is complete and ready to merge to `main`

**The PM never edits source files, runs tests, or writes implementation code.**

---

## Development Lifecycle (Coding Agents)

Every coding agent assigned a feature follows this loop until all assigned features are done:

```
1. Implement code
2. Implement tests
3. Lint          →  python3 -m ruff check src tests
4. Run tests     →  python3 -m pytest tests/ -q
5. Fix any failures and return to step 1
6. When all assigned features pass lint + tests → report completion
```

An agent is **not done** until:
- All assigned features are implemented
- All new and existing tests pass
- Lint reports zero errors

---

## PM Workflow

### Phase 1 — Plan

1. Read requirements (issue, conversation, or TODO)
2. Decompose into discrete features/tasks
3. Identify dependencies between features
4. Create a topic branch off `main`:
   ```bash
   git checkout -b feat/<topic>
   ```

### Phase 2 — Group & Assign

Group features by complexity:

| Complexity | Criteria | Model |
|------------|----------|-------|
| **Simple** | Single function, config change, or test addition | `haiku` |
| **Medium** | New module, multi-file change, or non-trivial logic | `sonnet` |
| **Complex** | Cross-cutting architectural change, new subsystem | `opus` |

### Phase 3 — Spawn Agents

For each feature group, spawn a coding agent using the Task tool with `isolation: "worktree"`:

```
subagent_type: Bash (for simple) or general-purpose (for medium/complex)
model: haiku | sonnet | opus (based on complexity group)
isolation: worktree
prompt: <detailed feature spec + dev lifecycle instructions>
```

Each agent prompt must include:
- The specific features to implement
- Relevant existing files to read first
- The dev lifecycle steps to follow
- How to report completion (summary of changes + test results)

### Phase 4 — Analyze & Merge

When an agent completes:

1. Read the agent's diff (`git diff main...<branch>`)
2. Verify: Do the changes match the assigned feature spec?
3. Verify: Are tests present and meaningful (not just passing trivially)?
4. Verify: No regressions in unrelated modules
5. If issues found: resume the agent with specific feedback
6. If satisfactory: merge into the topic branch:
   ```bash
   git merge --no-ff <worktree-branch> -m "feat: <description>"
   ```

### Phase 5 — QA Pass

Once all feature agents have merged into the topic branch:

1. Spawn one or more QA agents (`sonnet` or `opus`) with the task:
   - Review all changes on the topic branch vs `main`
   - Identify missing edge case tests
   - Identify code quality issues (dead code, unclear logic, missing type hints on public functions)
   - Identify any features from the original spec that were missed
2. Analyze QA agent reports
3. If gaps found: return to Phase 2 with the remaining work
4. If clean: merge topic branch to `main` with a conventional commit

### Phase 6 — Repeat

If new requirements emerge or QA finds significant gaps, repeat from Phase 1 with a new or extended topic branch.

---

## Branch Conventions

```
main              — always releasable
feat/<topic>      — topic branch owned by PM for a feature set
fix/<topic>       — bug fix topic branch
```

Worktree branches created by agents are ephemeral and managed by the `isolation: "worktree"` mechanism.

## Commit Conventions

```
feat: add overlay user setup for fedora instances
fix: skip sudoers setup on scratch-based containers
test: add config atomic write tests
refactor: extract base image detection to instance module
chore: update dependencies
docs: document overlay mode in README
```

---

## Project: scratch-monkey

### Tech Stack

- **Language**: Python 3.11+
- **Package manager**: pip (uv not available on this machine)
- **Build**: hatchling (`pyproject.toml`)
- **CLI**: Click
- **GUI**: Enaml + Qt6 (optional dep)
- **Tests**: pytest (135 tests, no real podman required)
- **Lint/format**: ruff

### Key Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Lint
python3 -m ruff check src tests

# Format
python3 -m ruff format src tests

# Test
python3 -m pytest tests/ -q

# Test with coverage
python3 -m pytest tests/ -q --tb=short
```

### Package Layout

```
src/scratch_monkey/
  config.py      — InstanceConfig dataclass, tomllib parse, atomic save
  container.py   — PodmanRunner (subprocess wrapper, fully mockable)
  instance.py    — create/clone/delete/list/skel lifecycle
  overlay.py     — overlay container management (scratch vs fedora detection)
  shared.py      — shared volume CRUD
  export.py      — export_command / unexport
  cli/main.py    — Click CLI (all user commands)
  gui/           — Enaml GUI (optional)
tests/
  conftest.py    — shared fixtures (mock_runner, instance fixtures)
  test_*.py      — unit tests per module
```

### Podman Boundary

All podman calls go through `PodmanRunner` in `container.py`. Tests mock at this boundary — no real podman process is ever started in unit tests. Any new module that needs to run podman commands must use `PodmanRunner`, not bare `subprocess.run`.

### Critical Design Decisions

- **Atomic config writes**: always use `config.save()`, never write scratch.toml directly
- **Fedora detection**: use `is_fedora_based(instance_dir)` which reads the **last** FROM line
- **Overlay user setup**: only runs for fedora instances; scratch instances skip entirely
- **Instance name validation**: always call `validate_name()` before creating/cloning
