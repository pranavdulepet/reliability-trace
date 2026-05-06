# Frontend Evidence Lab Concepts

This pass implements Concept A by default. All three concepts keep the existing chat-first workflow, left conversation rail, compact reliability summary, and one expandable analysis drawer.

## Concept A: Evidence Lab Default

Intent: calm research-product UI that feels trustworthy without becoming a dashboard.

- Empty chat: centered prompt area with short setup state, clear composer, quiet web-evidence status, and no marketing copy.
- Answered chat: answer first, inline citations next to supported spans, compact Reliability Score block directly under the cited sources.
- Expanded analysis drawer: tabbed evidence view with dense but readable rows, source-forward tables, and semantic status colors.
- Rail: slim slate rail, searchable list, compact delete control, Settings/About pinned at the bottom.
- Composer: one input, file attach, evidence status, send button. URLs are pasted directly into the input.
- Mobile: rail collapses to a top strip, conversations scroll horizontally, analysis tables become stacked rows.

## Concept B: Focus Thread

Intent: closest to ChatGPT/Claude, with reliability minimized until the user asks for more detail.

- Empty chat: sparse first screen with a single large input and a short readiness line.
- Answered chat: wide reading column, citations as compact chips, Reliability Score as a small summary row.
- Expanded analysis drawer: starts collapsed by default unless the decision is unsafe; fewer visible metrics until opened.
- Rail: visually recessive, with less metadata per conversation.
- Composer: floating, minimal controls, status hidden unless degraded.
- Mobile: answer column dominates; rail and settings move behind compact navigation.

## Concept C: Analyst Drawer

Intent: stronger Elicit-style evidence workspace for users who spend time auditing sources.

- Empty chat: chat remains primary, but the analysis drawer preview is visible as an empty evidence workspace.
- Answered chat: answer remains first, but evidence table gets more prominence immediately after the score.
- Expanded analysis drawer: persistent split view with source list on the left and claim/source detail on the right.
- Rail: same left rail, slightly denser conversation history for heavy usage.
- Composer: same simple input, with upload and evidence readiness controls.
- Mobile: drawer becomes a full-width stacked audit sheet.

## Selected Direction

Concept A is selected for this implementation because it balances a consumer-grade chat experience with the product's reliability purpose. It reduces clutter, keeps source evidence easy to reach, and avoids making normal chat feel intimidating.
