# TradingAgents Frontend Design Contract

## Intent
- Establish a shared workstation visual language for the authenticated application shell without forcing a one-shot layout rewrite.
- Move presentation away from one-off `slate`/`cyan` utility combinations toward semantic tokens that worker-2 and worker-3 can adopt incrementally.
- Preserve current frontend behavior while introducing a stable token vocabulary for surfaces, data emphasis, navigation, and status states.

## Visual Direction
- **Mood:** premium trading workstation, dark canvas, luminous data surfaces, restrained accent color.
- **Density:** compact by default, with enough spacing for multi-panel analysis workflows.
- **Emphasis model:** the background should recede; surfaces, charts, task state, and primary actions should carry focus.
- **Localization:** typography and spacing must remain comfortable for Chinese labels, mixed English symbols, and ticker codes.

## Semantic Token Vocabulary

### Foundations
- `bg-canvas` / `text-primary`: global shell background and primary foreground.
- `bg-surface`, `bg-surface-strong`, `bg-surface-elevated`: panel layers from outer shell to focused cards.
- `border-subtle`, `border-strong`: default and emphasized separation.
- `text-muted`, `text-subtle`: secondary and tertiary copy.
- `ring-accent`, `text-accent`, `bg-accent`: primary interactive highlight.
- `bg-positive`, `bg-caution`, `bg-negative`: semantic decision/status fills.

### Interaction + affordances
- `shadow-panel`, `shadow-glow`: standard panel elevation and accent emphasis.
- `rounded-panel`, `rounded-pill`: container and badge rounding.
- `bg-grid`, `bg-radial-focus`: shell atmosphere utilities for hero/header regions.
- `surface-panel`, `surface-panel-strong`, `surface-card`, `surface-interactive`: reusable CSS utility classes for workstation sections.

### Data presentation
- `text-label`: uppercase/meta labels.
- `text-data`: high-emphasis numeric or identifier values.
- `chip-accent`: compact accent badge/token.
- `status-positive`, `status-caution`, `status-negative`: pill treatments for decisions, warnings, and failures.
- `divider-subtle`: low-contrast separators for dense panes.

## Adoption Rules
- Prefer semantic tokens/classes over hard-coded `slate-*`, `cyan-*`, `emerald-*`, and `amber-*` combinations in new UI work.
- Use Tailwind color tokens when composing inside JSX; use the semantic CSS utility classes for repeated workstation patterns.
- Keep App composition changes minimal in this task. Larger layout adoption belongs to worker-2 and component-level styling belongs to worker-3.
- Existing light-theme primitives may coexist temporarily, but new workstation sections should migrate toward the semantic tokens above.

## Mapping from Legacy Utilities
- `bg-white/90`, `bg-slate-50/80`, `bg-slate-50/90` → `bg-surface` or `surface-card`
- `border-slate-200` → `border-subtle`
- `text-slate-950` → `text-primary`
- `text-slate-500` / `text-slate-400` → `text-muted` / `text-subtle`
- `bg-cyan-50`, `text-cyan-700`, `border-cyan-200/300` → `bg-accent-soft`, `text-accent`, `border-accent`
- `bg-emerald-50` / `text-emerald-700` → `bg-positive` / `text-positive`
- `bg-amber-50` / `text-amber-700` → `bg-caution` / `text-caution`

## Guardrails
- Do not change data flow, API/auth semantics, or test-facing exports when adopting this design contract.
- Avoid introducing a light/dark theme toggle in this phase; the contract assumes a single workstation visual system.
- Keep new tokens broad enough for analysis, memory, governance, and compliance screens so teams do not fork visual language per page.
