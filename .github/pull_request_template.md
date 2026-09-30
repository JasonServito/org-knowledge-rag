## Task

`S0X-TY`: <title>. Slice doc: `docs/slices/S0X-*.md`

## Brief

<!-- 8 lines or fewer. Core tasks may add the optional one-line Key code. -->

- **What changed:** 1–2 lines.
- **Decisions:** choice → alternative rejected → why, or "none".
- **How verified:** `make check` <result>; `make test-int` <result, if DB or integration paths changed>; `make eval-smoke` <metric deltas, if retrieval or generation changed>.
- **Interview-relevant:** 0–2 bullets, or "none".
- **Key code** (`core` only, optional): `file:function`, …

<details>
<summary>Check output</summary>

```
<paste the make check / make test-int output>
```

</details>

## Checklist

- [ ] Scope limited to this task; no unrelated edits
- [ ] No new dependency, service or pattern without an ADR
- [ ] No changes to `eval/golden_set/` (human-owned)
- [ ] Docs/ADR updated if behavior changed or a decision was made
- [ ] Backlog checkbox ticked
