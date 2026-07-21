<script lang="ts">
  export interface Crumb {
    id: string | null;
    label: string;
  }

  interface Props {
    items: Crumb[];
    onnavigate: (id: string | null) => void;
  }

  let { items, onnavigate }: Props = $props();
</script>

<nav class="breadcrumb" aria-label="Diagram level">
  {#each items as item, i (item.id ?? "root")}
    {#if i > 0}<span class="sep" aria-hidden="true">›</span>{/if}
    <button class="crumb" class:current={i === items.length - 1} disabled={i === items.length - 1} onclick={() => onnavigate(item.id)}>
      {item.label}
    </button>
  {/each}
</nav>

<style>
  .breadcrumb {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 2px;
    font-family: "Segoe UI", system-ui, sans-serif;
  }

  .crumb {
    background: none;
    border: none;
    color: var(--text-crumb, #2a5a9c);
    font-size: 13px;
    font-weight: 600;
    padding: 3px 7px;
    border-radius: 5px;
    cursor: pointer;
  }

  .crumb:hover:not(:disabled) {
    background: rgba(100, 140, 200, 0.12);
    color: var(--color-logo, #1a6fd6);
  }

  .crumb.current {
    color: var(--color-hint, #b85e00);
    cursor: default;
  }

  .sep {
    color: var(--text-secondary, #5a6d84);
    font-size: 14px;
  }
</style>
