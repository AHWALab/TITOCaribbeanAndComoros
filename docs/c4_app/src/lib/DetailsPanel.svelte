<script lang="ts">
  import { elements, relationships, hasChildren, type C4Element, type C4Kind } from "./c4Model";

  interface Props {
    element: C4Element | null;
    ondrill: (id: string) => void;
    onselect: (id: string) => void;
    onclose: () => void;
  }

  let { element, ondrill, onselect, onclose }: Props = $props();

  const KIND_LABEL: Record<C4Kind, string> = {
    person: "Person",
    system: "Software System",
    systemExt: "External System",
    container: "Container",
    containerDb: "Data Store",
    component: "Component",
  };

  const outgoing = $derived(element ? relationships.filter((r) => r.from === element.id) : []);
  const incoming = $derived(element ? relationships.filter((r) => r.to === element.id) : []);

  function name(id: string): string {
    return elements[id]?.name ?? id;
  }
</script>

{#if element}
  <aside class="panel">
    <div class="panel-head">
      <span class="kind kind-{element.kind}">{KIND_LABEL[element.kind]}</span>
      <button class="close" onclick={onclose} aria-label="Close details">×</button>
    </div>

    <h2 class="title">{element.name}</h2>
    {#if element.technology}<div class="tech">{element.technology}</div>{/if}
    <p class="desc">{element.description}</p>

    {#if hasChildren(element.id)}
      <button class="drill-btn" onclick={() => ondrill(element.id)}>
        Drill into {element.name} →
      </button>
      <section class="block">
        <h3>Contains</h3>
        <ul class="chip-list">
          {#each element.children ?? [] as childId (childId)}
            <li>
              <button class="chip" onclick={() => onselect(childId)}>{name(childId)}</button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if element.files && element.files.length > 0}
      <section class="block">
        <h3>Source</h3>
        <ul class="file-list">
          {#each element.files as file (file)}
            <li><code>{file}</code></li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if outgoing.length > 0}
      <section class="block">
        <h3>Uses / sends</h3>
        <ul class="rel-list">
          {#each outgoing as rel (rel.to + rel.label)}
            <li>
              <button class="rel" onclick={() => onselect(rel.to)}>{name(rel.to)}</button>
              <span class="rel-label">{rel.label}{rel.technology ? ` · ${rel.technology}` : ""}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if incoming.length > 0}
      <section class="block">
        <h3>Used by</h3>
        <ul class="rel-list">
          {#each incoming as rel (rel.from + rel.label)}
            <li>
              <button class="rel" onclick={() => onselect(rel.from)}>{name(rel.from)}</button>
              <span class="rel-label">{rel.label}{rel.technology ? ` · ${rel.technology}` : ""}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}
  </aside>
{/if}

<style>
  .panel {
    width: 340px;
    height: 100%;
    overflow-y: auto;
    background: var(--bg-panel, #ffffff);
    border-left: 1px solid var(--border-topbar, #dde3ea);
    padding: 16px 18px 28px;
    box-sizing: border-box;
    color: var(--text-primary, #1a2332);
    font-family: "Segoe UI", system-ui, sans-serif;
  }

  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .kind {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 4px;
    color: #fff;
  }
  .kind-person {
    background: #08427b;
  }
  .kind-system {
    background: #1168bd;
  }
  .kind-systemExt {
    background: #6b6b6b;
  }
  .kind-container {
    background: #438dd5;
  }
  .kind-containerDb {
    background: #3a7fb8;
  }
  .kind-component {
    background: #85bbf0;
    color: #0b2545;
  }

  .close {
    background: none;
    border: none;
    color: var(--text-secondary, #5a6d84);
    font-size: 22px;
    line-height: 1;
    cursor: pointer;
    padding: 0 4px;
  }
  .close:hover {
    color: var(--text-primary, #1a2332);
  }

  .title {
    font-size: 19px;
    margin: 12px 0 2px;
  }

  .tech {
    font-size: 12px;
    color: var(--text-secondary, #5a6d84);
    font-family: ui-monospace, "Cascadia Code", monospace;
    margin-bottom: 8px;
  }

  .desc {
    font-size: 13px;
    line-height: 1.5;
    color: var(--text-legend, #3a4d64);
  }

  .drill-btn {
    width: 100%;
    margin: 6px 0 4px;
    padding: 9px;
    background: #1168bd;
    color: #fff;
    border: none;
    border-radius: 6px;
    font-weight: 700;
    font-size: 13px;
    cursor: pointer;
  }
  .drill-btn:hover {
    background: #1a7ad6;
  }

  .block {
    margin-top: 18px;
  }
  .block h3 {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--text-secondary, #5a6d84);
    margin: 0 0 8px;
  }

  .chip-list,
  .file-list,
  .rel-list {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .chip-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    background: var(--bg-up-btn, #e8ecf1);
    border: 1px solid var(--border-up-btn, #c8d2dc);
    color: var(--text-primary, #1a2332);
    font-size: 12px;
    padding: 4px 9px;
    border-radius: 12px;
    cursor: pointer;
  }
  .chip:hover {
    background: var(--bg-up-btn-hover, #dce1e8);
  }

  .file-list li {
    margin-bottom: 5px;
  }
  .file-list code {
    font-size: 11.5px;
    background: var(--bg-view-title, #f0f2f5);
    color: #1a7a2e;
    padding: 3px 6px;
    border-radius: 4px;
    display: inline-block;
    word-break: break-all;
  }

  .rel-list li {
    margin-bottom: 9px;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .rel {
    align-self: flex-start;
    background: none;
    border: none;
    color: var(--text-crumb, #2a5a9c);
    font-size: 13px;
    font-weight: 600;
    padding: 0;
    cursor: pointer;
  }
  .rel:hover {
    color: var(--color-logo, #1a6fd6);
    text-decoration: underline;
  }
  .rel-label {
    font-size: 11px;
    color: var(--text-secondary, #5a6d84);
  }
</style>
