/**
 * Layout + edge construction for the C4 diagram.
 *
 * Layouts follow C4 conventions (https://c4model.com/):
 *   - System Context: Person at top, system at centre, external systems around.
 *   - Container / Component: Pipeline flow — hub at top, dependents in rows below
 *     showing the data flow direction. External entities on the periphery.
 *   - Fallback: layered top-down with row splitting for readability.
 */
import { MarkerType, type Node, type Edge } from "@xyflow/svelte";
import { elements, hasChildren, type C4View } from "./c4Model";

const COL_W = 300;
const ROW_H = 200;
const MAX_PER_ROW = 6;

export type C4Role = "boundary" | "external" | "hub";

function roleOf(view: C4View, id: string): C4Role {
  if (elements[id]?.hub) return "hub";
  return view.boundaryIds.includes(id) ? "boundary" : "external";
}

function makeNode(id: string, x: number, y: number, role: C4Role, selectedId: string | null): Node {
  return {
    id,
    type: "c4",
    position: { x, y },
    data: { element: elements[id], role, drillable: hasChildren(id) },
    selected: id === selectedId,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────────────────────────────────

export function buildNodes(view: C4View, selectedId: string | null): Node[] {
  if (view.id === "context") {
    return buildSystemContext(view, selectedId);
  }

  // For container/component levels with a hub: pipeline flow (top → bottom).
  const hubId = [...view.boundaryIds, ...view.externalIds].find((id) => elements[id]?.hub);
  if (hubId) {
    return buildPipelineFlow(view, hubId, selectedId);
  }

  return buildLayered(view, selectedId);
}

// ─────────────────────────────────────────────────────────────────────────
// System Context — manual C4 layout
// ─────────────────────────────────────────────────────────────────────────

function buildSystemContext(view: C4View, selectedId: string | null): Node[] {
  const CANVAS_CX = 600;
  const out: Node[] = [];

  const place = (id: string, cx: number, cy: number, role: C4Role) => {
    const el = elements[id];
    const w = el?.hub ? 270 : 230;
    out.push(makeNode(id, cx - w / 2, cy, role, selectedId));
  };

  place("operator", CANVAS_CX, 0, view.externalIds.includes("operator") ? "external" : "boundary");

  const EXTERNAL_L = CANVAS_CX - 435;
  const EXTERNAL_R = CANVAS_CX + 435;

  place("nasa_gpm", EXTERNAL_L, 200, "external");
  place("scampr", EXTERNAL_L, 370, "external");

  place("tito", CANVAS_CX, 220, "hub");

  place("noaa_gfs", EXTERNAL_R, 200, "external");
  place("arome", EXTERNAL_R, 370, "external");

  place("merra2", CANVAS_CX, 460, "external");

  return out;
}

// ─────────────────────────────────────────────────────────────────────────
// Pipeline flow — hub at top, rows below follow data-flow distance.
// ─────────────────────────────────────────────────────────────────────────
//
// External elements are pushed to the last row so they read as "context."
// The hub sits alone in row 0; rows 1..N contain boundary elements ordered
// by BFS distance from the hub.

function buildPipelineFlow(view: C4View, hubId: string, selectedId: string | null): Node[] {
  const boundarySet = new Set(view.boundaryIds);
  const allIds = [...view.boundaryIds, ...view.externalIds].filter((id) => elements[id]);
  const idSet = new Set(allIds);
  const rels = view.rels.filter((r) => idSet.has(r.from) && idSet.has(r.to) && r.from !== r.to);

  // BFS from hub over boundary elements only.
  const dist = new Map<string, number>();
  dist.set(hubId, 0);
  const queue = [hubId];
  while (queue.length) {
    const cur = queue.shift()!;
    const d = dist.get(cur)! + 1;
    for (const r of rels) {
      for (const nxt of [r.from === cur ? r.to : null, r.to === cur ? r.from : null]) {
        if (nxt && !dist.has(nxt) && boundarySet.has(nxt)) {
          dist.set(nxt, d);
          queue.push(nxt);
        }
      }
    }
  }

  // Group boundary elements by distance (row 1 = distance 1, etc.).
  const maxDist = Math.max(1, ...dist.values());
  const rows: string[][] = [[hubId]];
  for (let d = 1; d <= maxDist; d++) {
    rows[d] = [];
  }
  // Any boundary element not reached goes to the last row.
  const lastRow = maxDist + 1;
  rows[lastRow] = [];

  for (const id of view.boundaryIds) {
    if (id === hubId) continue;
    const d = dist.get(id);
    if (d !== undefined && d <= maxDist) {
      rows[d]!.push(id);
    } else {
      rows[lastRow]!.push(id);
    }
  }

  // Operator (person) always at the top — insert as a row before the hub.
  const hasOperator = view.externalIds.includes("operator") && elements["operator"];
  if (hasOperator) {
    rows.unshift(["operator"]);
  }

  // External elements (except operator) in the final row.
  const extIds = view.externalIds.filter((id) => elements[id] && id !== hubId && id !== "operator");
  if (extIds.length > 0) {
    rows.push(extIds);
  }

  // Remove empty rows.
  const filledRows = rows.filter((r) => r && r.length > 0);

  // Compute positions — centre each row.
  const widest = filledRows.reduce((m, r) => Math.max(m, r.length), 1);
  const centerX = (widest * COL_W) / 2;
  const HUB_W = elements[hubId]?.hub ? 270 : 230;

  const out: Node[] = [];
  for (let r = 0; r < filledRows.length; r++) {
    const row = filledRows[r];
    const startX = centerX - (row.length * COL_W) / 2;
    for (let i = 0; i < row.length; i++) {
      const id = row[i];
      let x: number;
      let y: number;

      if (id === hubId) {
        // Hub is wider — centre it in its column.
        x = centerX - HUB_W / 2;
        y = r * ROW_H;
      } else {
        x = startX + i * COL_W;
        y = r * ROW_H;
      }
      const role = roleOf(view, id);
      out.push(makeNode(id, Math.round(x), Math.round(y), role, selectedId));
    }
  }

  return out;
}

// ─────────────────────────────────────────────────────────────────────────
// Layered top-down — fallback layout.
// ─────────────────────────────────────────────────────────────────────────

function buildLayered(view: C4View, selectedId: string | null): Node[] {
  const ids = Array.from(new Set([...view.boundaryIds, ...view.externalIds])).filter((id) => elements[id]);
  const idSet = new Set(ids);
  const rels = view.rels.filter((r) => idSet.has(r.from) && idSet.has(r.to) && r.from !== r.to);

  const preds = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const r of rels) preds.get(r.to)!.push(r.from);

  const layer = new Map<string, number>(ids.map((id) => [id, 0]));
  for (let k = 0; k < ids.length; k++) {
    let changed = false;
    for (const r of rels) {
      const next = layer.get(r.from)! + 1;
      if (next > layer.get(r.to)!) {
        layer.set(r.to, next);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const maxLayer = ids.reduce((m, id) => Math.max(m, layer.get(id)!), 0);
  const rawRows: string[][] = [];
  for (let l = 0; l <= maxLayer; l++) rawRows[l] = ids.filter((id) => layer.get(id) === l);

  const pos = new Map<string, number>();
  rawRows[0]?.forEach((id, i) => pos.set(id, i));
  for (let l = 1; l <= maxLayer; l++) {
    const bary = (id: string): number => {
      const ps = preds.get(id)!.filter((p) => pos.has(p));
      if (ps.length === 0) return Number.POSITIVE_INFINITY;
      return ps.reduce((s, p) => s + pos.get(p)!, 0) / ps.length;
    };
    rawRows[l].sort((a, b) => bary(a) - bary(b));
    rawRows[l].forEach((id, i) => pos.set(id, i));
  }

  const splitRows: string[][] = [];
  for (const row of rawRows) {
    while (row.length > MAX_PER_ROW) {
      splitRows.push(row.splice(0, MAX_PER_ROW));
    }
    if (row.length > 0) splitRows.push(row);
  }

  const widest = splitRows.reduce((m, r) => Math.max(m, r.length), 1);
  const centerX = (widest * COL_W) / 2;

  const out: Node[] = [];
  for (let l = 0; l < splitRows.length; l++) {
    const row = splitRows[l];
    const startX = centerX - (row.length * COL_W) / 2;
    row.forEach((id, i) => {
      out.push(makeNode(id, startX + i * COL_W, l * ROW_H, roleOf(view, id), selectedId));
    });
  }
  return out;
}

export function buildEdges(view: C4View): Edge[] {
  // Label appearance is themed via global CSS (.svelte-flow__edge-label) in
  // Diagram.svelte, since the label renders as an HTML element.
  return view.rels.map((r, idx) => ({
    id: `${r.from}__${r.to}__${idx}`,
    source: r.from,
    target: r.to,
    label: r.label,
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: "#7a8aa0" },
    style: "stroke: #7a8aa0; stroke-width: 1.5;",
  }));
}
