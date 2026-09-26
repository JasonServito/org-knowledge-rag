---
name: explain
description: Teach the developer how a file, function, concept, or design decision in this project works, and why, at new-grad level with interview framing. Use when the user asks to explain code, a concept, or a trade-off.
---

# Explain

The developer is a new-grad SWE who must defend this project in interviews.

1. Read the relevant code and any ADR, spec or slice sections that govern it.
2. Explain, in this order:
   - **Purpose:** what problem this solves in the project (one paragraph).
   - **How it works:** walk through the flow in plain language, then point to the key lines (`file:function`).
   - **Why it's designed this way:** the reasoning, the main alternative, and the trade-off. Cite the ADR if one exists.
   - **Concepts:** define each piece of jargon on first use.
   - **Failure modes:** what breaks it, and how we'd notice (tests, metrics).
   - **Interview angle:** 2–3 questions an interviewer might ask, with short answer sketches.
3. End with one question for the developer, to check understanding. Don't answer it.
4. Keep it proportional: a small function gets a short explanation. Don't pad.
