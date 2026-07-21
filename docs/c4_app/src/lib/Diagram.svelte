<script lang="ts">
  import { SvelteFlow, Background, Controls, MiniMap, type Node, type Edge } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";

  import C4Node from "./C4Node.svelte";
  import { hasChildren, type C4View } from "./c4Model";
  import { buildNodes, buildEdges } from "./layout";

  interface Props {
    view: C4View;
    selectedId: string | null;
    ondrill: (id: string) => void;
    onselect: (id: string) => void;
  }

  let { view, selectedId, ondrill, onselect }: Props = $props();

  const nodeTypes = { c4: C4Node };

  // Read-only viewer: derive nodes/edges from the current view. The parent
  // re-keys this component per level, so Svelte Flow re-fits the viewport.
  const nodes = $derived<Node[]>(buildNodes(view, selectedId));
  const edges = $derived<Edge[]>(buildEdges(view));

  function handleNodeClick(id: string) {
    onselect(id);
    if (hasChildren(id)) ondrill(id);
  }
</script>

<div class="diagram">
  <SvelteFlow
    {nodes}
    {edges}
    {nodeTypes}
    fitView
    fitViewOptions={{ padding: 0.18 }}
    minZoom={0.2}
    maxZoom={2}
    nodesDraggable={false}
    nodesConnectable={false}
    elementsSelectable={true}
    proOptions={{ hideAttribution: true }}
    onnodeclick={({ node }) => handleNodeClick(node.id)}
  >
    <Background bgColor="var(--canvas-dot)" patternColor="var(--canvas-line)" gap={22} />
    <Controls showLock={false} />
    <MiniMap pannable zoomable nodeColor="var(--minimap-node)" maskColor="var(--minimap-mask)" />
  </SvelteFlow>
</div>

<style>
  .diagram {
    width: 100%;
    height: 100%;
  }

  /* Edge labels render as HTML .svelte-flow__edge-label divs. */
  .diagram :global(.svelte-flow__edge-label) {
    background: var(--edge-label-bg);
    color: var(--edge-label-color);
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 5px;
    border: 1px solid var(--edge-label-border);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  }
</style>
