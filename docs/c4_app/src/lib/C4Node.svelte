<script lang="ts">
  import { Handle, Position, type NodeProps } from "@xyflow/svelte";
  import type { C4Element, C4Kind } from "./c4Model";

  interface C4NodeData {
    element: C4Element;
    role: "boundary" | "external" | "hub";
    drillable: boolean;
  }

  let { data, selected }: NodeProps = $props();

  const d = $derived(data as unknown as C4NodeData);
  const el = $derived(d.element);

  const KIND_LABEL: Record<C4Kind, string> = {
    person: "Person",
    system: "Software System",
    systemExt: "External System",
    container: "Container",
    containerDb: "Data Store",
    component: "Component",
  };
</script>

<div class="c4-node {el.kind} {d.role}" class:drillable={d.drillable} class:is-selected={selected} title={el.description}>
  <Handle type="target" position={Position.Top} class="c4-handle" isConnectable={false} />

  <div class="kind-tag">{KIND_LABEL[el.kind]}</div>
  <div class="name">{el.name}</div>
  {#if el.technology}
    <div class="tech">[{el.technology}]</div>
  {/if}
  <div class="desc">{el.description}</div>
  {#if d.drillable}
    <div class="drill-hint">＋ click to drill in</div>
  {/if}

  <Handle type="source" position={Position.Bottom} class="c4-handle" isConnectable={false} />
</div>

<style>
  .c4-node {
    /* Per-node theming: dark-background nodes use light text, light-background
		   nodes override these to dark text for readable contrast. */
    --ink: #fff;
    --ink-soft: rgba(255, 255, 255, 0.82);
    --accent: #ffd166;

    box-sizing: border-box;
    width: 230px;
    min-height: 110px;
    padding: 10px 12px;
    border-radius: 6px;
    border: 2px solid rgba(0, 0, 0, 0.18);
    color: var(--ink);
    font-family: "Segoe UI", system-ui, sans-serif;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    cursor: pointer;
    transition:
      transform 0.08s ease,
      box-shadow 0.12s ease;
  }

  .c4-node:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.2);
  }

  .c4-node.is-selected {
    outline: 3px solid #ffd166;
    outline-offset: 2px;
  }

  /* ── C4 notation colors ─────────────────────────────────────── */
  .person {
    background: #08427b;
    border-radius: 30px / 18px;
  }
  .system {
    background: #1168bd;
  }
  .systemExt {
    background: #6b6b6b;
  }
  .container {
    background: #438dd5;
  }
  .containerDb {
    background: #3a7fb8;
    border-radius: 6px 6px 14px 14px;
  }
  /* Light background -> dark ink + dark accent so all text stays readable. */
  .component {
    background: #85bbf0;
    --ink: #0a2540;
    --ink-soft: rgba(10, 37, 64, 0.78);
    --accent: #9a4a00;
  }

  /* External (context) elements render muted/dashed regardless of kind. */
  .external {
    opacity: 0.9;
    border-style: dashed;
    filter: saturate(0.7);
  }

  /* Hub (e.g. the Orchestrator) is emphasized as the center of its level. */
  .hub {
    width: 270px;
    min-height: 130px;
    box-shadow:
      0 0 0 3px rgba(255, 209, 102, 0.5),
      0 6px 24px rgba(0, 0, 0, 0.25);
  }
  .hub .name {
    font-size: 16px;
  }

  .drillable {
    border-color: #ffd166;
  }

  .kind-tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--ink-soft);
    margin-bottom: 2px;
  }

  .name {
    font-size: 14px;
    font-weight: 700;
    line-height: 1.2;
    color: var(--ink);
  }

  .tech {
    font-size: 10px;
    color: var(--ink-soft);
    margin-top: 1px;
  }

  .desc {
    font-size: 10.5px;
    line-height: 1.25;
    margin-top: 6px;
    color: var(--ink-soft);
    display: -webkit-box;
    -webkit-line-clamp: 4;
    line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .drill-hint {
    margin-top: 7px;
    font-size: 9.5px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.03em;
  }

  :global(.c4-handle) {
    opacity: 0;
    pointer-events: none;
  }
</style>
