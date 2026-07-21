<script lang="ts">
  import Diagram from "$lib/Diagram.svelte";
  import Breadcrumb, { type Crumb } from "$lib/Breadcrumb.svelte";
  import DetailsPanel from "$lib/DetailsPanel.svelte";
  import { elements, contextView, elementView, ancestors, hasChildren, type C4View } from "$lib/c4Model";

  // null = top-level system context; otherwise the id of the drilled-in element.
  let currentRootId = $state<string | null>(null);
  let selectedId = $state<string | null>(null);
  let showLegend = $state(true);
  let theme = $state<"dark" | "light">("light");

  const view: C4View = $derived(currentRootId ? elementView(currentRootId) : contextView());

  const crumbs: Crumb[] = $derived.by(() => {
    const items: Crumb[] = [{ id: null, label: "System Context" }];
    if (currentRootId) {
      for (const a of ancestors(currentRootId)) {
        items.push({ id: a, label: elements[a]?.name ?? a });
      }
      items.push({ id: currentRootId, label: elements[currentRootId]?.name ?? currentRootId });
    }
    return items;
  });

  const selectedElement = $derived(selectedId ? (elements[selectedId] ?? null) : null);

  const legend: { kind: string; label: string }[] = [
    { kind: "person", label: "Person" },
    { kind: "system", label: "Software System" },
    { kind: "systemExt", label: "External System" },
    { kind: "container", label: "Container" },
    { kind: "containerDb", label: "Data Store" },
    { kind: "component", label: "Component" },
  ];

  function drill(id: string) {
    if (!hasChildren(id)) return;
    currentRootId = id;
    selectedId = id;
  }

  function navigate(id: string | null) {
    currentRootId = id;
    selectedId = id;
  }

  function select(id: string) {
    selectedId = id;
  }

  function goUp() {
    if (!currentRootId) return;
    const chain = ancestors(currentRootId);
    navigate(chain.length ? chain[chain.length - 1] : null);
  }
</script>

<svelte:head>
  <title>TITO — Interactive C4 Model</title>
</svelte:head>

<div class="app" data-theme={theme}>
  <header class="topbar">
    <div class="brand">
      <span class="logo">TITO</span>
      <span class="subtitle">Interactive C4 Model</span>
    </div>
    <div class="nav">
      <button class="up" onclick={goUp} disabled={!currentRootId} title="Go up one level">↑ Up</button>
      <Breadcrumb items={crumbs} onnavigate={navigate} />
    </div>
    <button class="theme-toggle" onclick={() => (theme = theme === "dark" ? "light" : "dark")}>
      {theme === "dark" ? "☀" : "☾"}
    </button>
    <button class="legend-toggle" onclick={() => (showLegend = !showLegend)}>
      {showLegend ? "Hide" : "Show"} legend
    </button>
  </header>

  <div class="view-title">
    <h1>{view.title}</h1>
    <p>{view.subtitle}</p>
  </div>

  <main class="stage">
    <div class="canvas">
      {#key view.id}
        <Diagram {view} {selectedId} ondrill={drill} onselect={select} />
      {/key}

      {#if showLegend}
        <div class="legend">
          {#each legend as item (item.kind)}
            <div class="legend-row">
              <span class="swatch sw-{item.kind}"></span>
              <span>{item.label}</span>
            </div>
          {/each}
          <div class="legend-row hint">
            <span class="swatch sw-drill"></span>
            <span>Gold border = drillable</span>
          </div>
        </div>
      {/if}
    </div>

    {#if selectedElement}
      <DetailsPanel element={selectedElement} ondrill={drill} onselect={select} onclose={() => (selectedId = null)} />
    {/if}
  </main>
</div>

<style>
  /* ── Theme CSS custom properties ─────────────────────────────────── */
  :root,
  .app[data-theme="dark"] {
    --bg-body: #0d1526;
    --bg-topbar: #0a1120;
    --bg-view-title: #0b1322;
    --bg-canvas: #0d1526;
    --bg-panel: #111a2e;
    --bg-legend: rgba(12, 19, 34, 0.92);
    --bg-up-btn: #182742;
    --bg-up-btn-hover: #21355a;
    --bg-toggle-hover: #182742;

    --text-primary: #e7eefb;
    --text-secondary: #7e8eae;
    --text-legend: #c4d2ea;
    --text-crumb: #8fb6e8;

    --border-topbar: #1c2840;
    --border-view-title: #16203a;
    --border-up-btn: #29405f;
    --border-toggle: #29405f;
    --border-legend: #233352;
    --border-legend-hint: #233352;

    --color-logo: #4da3ff;
    --color-hint: #ffd166;

    --edge-label-bg: #16203a;
    --edge-label-color: #dfe7f3;
    --edge-label-border: #2c3a5a;

    --canvas-dot: #0d1526;
    --canvas-line: #1f2c47;
    --minimap-node: #2a3a5c;
    --minimap-mask: rgba(7, 12, 24, 0.7);
  }

  .app[data-theme="light"] {
    --bg-body: #f4f6f9;
    --bg-topbar: #ffffff;
    --bg-view-title: #f0f2f5;
    --bg-canvas: #ffffff;
    --bg-panel: #ffffff;
    --bg-legend: rgba(255, 255, 255, 0.94);
    --bg-up-btn: #e8ecf1;
    --bg-up-btn-hover: #dce1e8;
    --bg-toggle-hover: #e8ecf1;

    --text-primary: #1a2332;
    --text-secondary: #5a6d84;
    --text-legend: #3a4d64;
    --text-crumb: #2a5a9c;

    --border-topbar: #dde3ea;
    --border-view-title: #dde3ea;
    --border-up-btn: #c8d2dc;
    --border-toggle: #c8d2dc;
    --border-legend: #d0d7e0;
    --border-legend-hint: #d0d7e0;

    --color-logo: #1a6fd6;
    --color-hint: #b85e00;

    --edge-label-bg: #e8ecf1;
    --edge-label-color: #1a2332;
    --edge-label-border: #c8d2dc;

    --canvas-dot: #f0f4f8;
    --canvas-line: #dde3ea;
    --minimap-node: #c8d6e5;
    --minimap-mask: rgba(200, 210, 225, 0.5);
  }

  :global(html, body) {
    margin: 0;
    height: 100%;
    background: var(--bg-body);
  }
  :global(body) {
    overflow: hidden;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    color: var(--text-primary);
    font-family: "Segoe UI", system-ui, sans-serif;
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 10px 18px;
    background: var(--bg-topbar);
    border-bottom: 1px solid var(--border-topbar);
  }

  .brand {
    display: flex;
    align-items: baseline;
    gap: 9px;
  }
  .logo {
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.04em;
    color: var(--color-logo);
  }
  .subtitle {
    font-size: 12px;
    color: var(--text-secondary);
  }

  .nav {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
  }

  .up {
    background: var(--bg-up-btn);
    color: var(--text-primary);
    border: 1px solid var(--border-up-btn);
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 10px;
    cursor: pointer;
  }
  .up:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .up:hover:not(:disabled) {
    background: var(--bg-up-btn-hover);
  }

  .theme-toggle {
    background: none;
    border: 1px solid var(--border-toggle);
    color: var(--text-primary);
    border-radius: 6px;
    font-size: 15px;
    padding: 4px 9px;
    cursor: pointer;
    line-height: 1;
  }
  .theme-toggle:hover {
    background: var(--bg-toggle-hover);
  }

  .legend-toggle {
    background: none;
    border: 1px solid var(--border-toggle);
    color: var(--text-secondary);
    border-radius: 6px;
    font-size: 12px;
    padding: 5px 10px;
    cursor: pointer;
  }
  .legend-toggle:hover {
    background: var(--bg-toggle-hover);
  }

  .view-title {
    padding: 9px 20px;
    background: var(--bg-view-title);
    border-bottom: 1px solid var(--border-view-title);
  }
  .view-title h1 {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
  }
  .view-title p {
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .stage {
    flex: 1;
    display: flex;
    min-height: 0;
  }

  .canvas {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .legend {
    position: absolute;
    left: 14px;
    bottom: 14px;
    background: var(--bg-legend);
    border: 1px solid var(--border-legend);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 11.5px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    z-index: 5;
  }
  .legend-row {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-legend);
  }
  .legend-row.hint {
    margin-top: 3px;
    padding-top: 6px;
    border-top: 1px solid var(--border-legend-hint);
    color: var(--color-hint);
  }
  .swatch {
    width: 16px;
    height: 12px;
    border-radius: 3px;
    border: 1px solid rgba(128, 128, 128, 0.3);
    display: inline-block;
  }
  .sw-person {
    background: #08427b;
  }
  .sw-system {
    background: #1168bd;
  }
  .sw-systemExt {
    background: #6b6b6b;
  }
  .sw-container {
    background: #438dd5;
  }
  .sw-containerDb {
    background: #3a7fb8;
  }
  .sw-component {
    background: #85bbf0;
  }
  .sw-drill {
    background: transparent;
    border: 2px solid #ffd166;
  }
</style>
