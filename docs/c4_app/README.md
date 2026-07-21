# TITO — Interactive C4 Model

A small, local Svelte app that renders TITO's [C4 model](https://c4model.com/) as an
**interactive, drill-down diagram**. Click a system / container / component to reveal its
children; use the breadcrumb (or the **↑ Up** button) to navigate back; click any element to
open a details panel with its description, source files, and relationships.

The architecture data is hand-encoded in [`src/lib/c4Model.ts`](src/lib/c4Model.ts) from the
PlantUML diagrams in [`../c4_diagrams/`](../c4_diagrams) and the TITO codebase. It is the single
source of truth — edit it to add/adjust elements, relationships, or drill-down links.

## Levels

| Level | View | What you see |
| ----- | ---- | ------------ |
| 1 | System Context | People, external systems, and the TITO platform |
| 2 | Containers (click **TITO**) | Orchestrator, Precipitation Pipeline, STREAM-Sat Engine, EF5 Builder/Runner, stores, … |
| 3 | Components (click a container) | Internals of the Orchestrator, STREAM-Sat, Precipitation Pipeline, and EF5 Builder |

Elements with a **gold border** can be drilled into.

## Run locally

```sh
npm install      # first time only
npm run dev      # serves at http://localhost:5173
```

## Other commands

```sh
npm run check    # type-check (svelte-check)
npm run build    # static build into build/ (deployable to e.g. GitHub Pages later)
npm run preview  # preview the production build
```

## Tech

- SvelteKit + Svelte 5 (runes), TypeScript
- [`@xyflow/svelte`](https://svelteflow.dev) (Svelte Flow) for the interactive canvas (pan / zoom / click)
- `@sveltejs/adapter-static` (SPA) so a production build is a plain static site
