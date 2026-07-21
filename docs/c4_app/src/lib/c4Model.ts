/**
 * TITO — C4 model (single source of truth)
 * =========================================
 * Simplified model focused on the operational forecast flow:
 *
 *   Config → Orchestrator → QPE / QPF → EF5 Builder → EF5 Runner → Output
 *                                    ↘ State Manager (manages states)
 *
 * All file-based storage (precip, states, outputs, templates) is a single
 * "Local File Storage" container.
 */

export type C4Kind = "person" | "system" | "systemExt" | "container" | "containerDb" | "component";

export interface C4Element {
  id: string;
  name: string;
  kind: C4Kind;
  technology?: string;
  description: string;
  parent?: string;
  children?: string[];
  childLabel?: string;
  hub?: boolean;
  files?: string[];
}

export interface C4Rel {
  from: string;
  to: string;
  label: string;
  technology?: string;
}

export interface C4View {
  id: string;
  title: string;
  subtitle: string;
  rootId: string | null;
  boundaryIds: string[];
  externalIds: string[];
  rels: C4Rel[];
}

// ─────────────────────────────────────────────────────────────────────────
// Elements
// ─────────────────────────────────────────────────────────────────────────

export const elements: Record<string, C4Element> = {
  // ── Person ──────────────────────────────────────────────────────────
  operator: {
    id: "operator",
    name: "Operator / Hydrologist",
    kind: "person",
    description: "Triggers the hourly operational forecast (also supports hindcast) and edits the run configuration.",
  },

  // ── External data sources ───────────────────────────────────────────
  nasa_gpm: {
    id: "nasa_gpm",
    name: "NASA GPM IMERG",
    kind: "systemExt",
    technology: "Satellite QPE",
    description: "30-min, 0.1° satellite precipitation estimate. Primary QPE source.",
  },
  scampr: {
    id: "scampr",
    name: "NOAA SCaMPR",
    kind: "systemExt",
    technology: "IR QPE",
    description: "Blended IR rain-rate (~30 min latency). Fills the IMERG gap.",
  },
  noaa_gfs: {
    id: "noaa_gfs",
    name: "NOAA GFS",
    kind: "systemExt",
    technology: "NWP QPF + winds",
    description: "Global forecast — QPF and 850 hPa U/V wind fields.",
  },
  arome: {
    id: "arome",
    name: "Meteo-France AROME",
    kind: "systemExt",
    technology: "Regional NWP QPF",
    description: "High-resolution (2.5 km) forecast for ANTIL & INDIEN domains.",
  },
  merra2: {
    id: "merra2",
    name: "NASA MERRA2",
    kind: "systemExt",
    technology: "Reanalysis winds",
    description: "U850/V850 wind fields for STREAM-Sat noise advection.",
  },

  // ── TITO (System Context focus) ─────────────────────────────────────
  tito: {
    id: "tito",
    name: "TITO",
    kind: "system",
    hub: true,
    technology: "Hydrologic Forecasting Platform",
    description: "Downloads QPE/QPF, runs the EF5 hydrologic model per region, and manages model states for flash-flood forecasting.",
    childLabel: "Containers",
    children: ["orchestrator", "config_store", "qpe_pipeline", "qpf_pipeline", "ef5_builder", "ef5_runner", "state_mgr", "file_store"],
  },

  // ── Containers ──────────────────────────────────────────────────────
  orchestrator: {
    id: "orchestrator",
    name: "TITO Orchestrator",
    kind: "container",
    technology: "Python 3",
    parent: "tito",
    hub: true,
    childLabel: "Components",
    description: "Central hub. Reads the config, triggers precipitation pipelines, builds EF5 jobs, runs simulations, manages states.",
    files: ["orchestrator.py"],
    children: ["main_ctl", "ef5_exec", "state_comp"],
  },
  config_store: {
    id: "config_store",
    name: "Configuration",
    kind: "containerDb",
    technology: "Python config",
    parent: "tito",
    description: "Regions, QPE/QPF sources, paths, resolution, timestep. Drives every run.",
    files: ["Caribbean_Comoros_config.py"],
  },
  qpe_pipeline: {
    id: "qpe_pipeline",
    name: "QPE Pipeline",
    kind: "container",
    technology: "Python",
    parent: "tito",
    childLabel: "QPE Sources",
    description: "Quantitative Precipitation Estimate (observed rainfall). IMERG, SCaMPR, STREAM-Sat.",
    files: ["tito_utils/qpe_utils/"],
    children: ["imerg_src", "scampr_src", "stream_sat"],
  },
  qpf_pipeline: {
    id: "qpf_pipeline",
    name: "QPF Pipeline",
    kind: "container",
    technology: "Python",
    parent: "tito",
    childLabel: "QPF Sources",
    description: "Quantitative Precipitation Forecast (T → T+24h). GFS (QPF + winds) and AROME.",
    files: ["tito_utils/qpf_utils/"],
    children: ["gfs_src", "arome_src"],
  },
  ef5_builder: {
    id: "ef5_builder",
    name: "EF5 Job Builder",
    kind: "container",
    technology: "Python",
    parent: "tito",
    childLabel: "Components",
    description: "Generates EF5 control files from templates, stages precip, locates model states.",
    files: ["tito_utils/ef5/ef5_routines.py"],
    children: ["prepare_ef5", "control_filler", "precip_stager", "state_finder"],
  },
  ef5_runner: {
    id: "ef5_runner",
    name: "EF5 Simulation Runner",
    kind: "container",
    technology: "Python subprocess",
    parent: "tito",
    description: "Parallel executor across regions, ensemble members & QPF sources.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },
  state_mgr: {
    id: "state_mgr",
    name: "State Manager",
    kind: "container",
    technology: "File-based",
    parent: "tito",
    description: "Finds and manages model states. 7-day lookback for warm starts.",
  },
  file_store: {
    id: "file_store",
    name: "Local File Storage",
    kind: "containerDb",
    technology: "GeoTIFF + CSV + text",
    parent: "tito",
    description: "precip/, states/, outputs/, templates/ — all EF5 input/output stored as local files.",
  },

  // ── QPE sub-modules ─────────────────────────────────────────────────
  imerg_src: {
    id: "imerg_src",
    name: "IMERG QPE",
    kind: "component",
    technology: "imerg_retrieve.py",
    parent: "qpe_pipeline",
    description: "Downloads IMERG Early V07, warps/clips to domain, writes 30-min GeoTIFFs.",
    files: ["tito_utils/qpe_utils/imerg_retrieve.py"],
  },
  scampr_src: {
    id: "scampr_src",
    name: "SCaMPR QPE",
    kind: "component",
    technology: "scampr_retrieve.py",
    parent: "qpe_pipeline",
    description: "Fetches SCaMPR IR rain-rate from AWS S3, clips to domain.",
    files: ["tito_utils/qpe_utils/scampr_retrieve.py"],
  },
  stream_sat: {
    id: "stream_sat",
    name: "STREAM-Sat Engine",
    kind: "container",
    technology: "Python + netCDF4",
    parent: "qpe_pipeline",
    childLabel: "Components",
    description: "Ensemble QPE via CSGD error model + anisotropic noise → N-member GeoTIFFs.",
    files: ["STREAM-Sat-realtime/", "tito_utils/qpe_utils/stream_sat_utils.py"],
    children: ["rt_pipeline", "noise_gen", "precip_sim", "wind_adapter", "state_persist", "nc2tif"],
  },

  // ── QPF sub-modules ─────────────────────────────────────────────────
  gfs_src: {
    id: "gfs_src",
    name: "GFS QPF & Winds",
    kind: "component",
    technology: "gfs_manager.py",
    parent: "qpf_pipeline",
    description: "Downloads GFS QPF and 850 hPa U/V winds from NOAA, converts to GeoTIFF.",
    files: ["tito_utils/qpf_utils/gfs_manager.py"],
  },
  arome_src: {
    id: "arome_src",
    name: "AROME QPF",
    kind: "component",
    technology: "arome_manager.py",
    parent: "qpf_pipeline",
    description: "Downloads AROME QPF for ANTIL (Caribbean) or INDIEN (Comoros) domains.",
    files: ["tito_utils/qpf_utils/arome_manager.py"],
  },

  // ── Orchestrator components ─────────────────────────────────────────
  main_ctl: {
    id: "main_ctl",
    name: "Main Controller",
    kind: "component",
    technology: "main()",
    parent: "orchestrator",
    description: "Entry point. Loads config, runs QPE/QPF, builds & executes EF5 jobs each cycle.",
    files: ["orchestrator.py"],
  },
  ef5_exec: {
    id: "ef5_exec",
    name: "EF5 Execution Engine",
    kind: "component",
    technology: "run_ef5_simulations_parallel()",
    parent: "orchestrator",
    description: "ThreadPool-based parallel EF5 runner across all regions and ensemble members.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },
  state_comp: {
    id: "state_comp",
    name: "State Manager",
    kind: "component",
    technology: "find_available_states()",
    parent: "orchestrator",
    description: "7-day backward search for viable model states. Cold-start detection.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },

  // ── STREAM-Sat components ───────────────────────────────────────────
  rt_pipeline: {
    id: "rt_pipeline",
    name: "Real-time Pipeline",
    kind: "component",
    technology: "run_pipeline.py",
    parent: "stream_sat",
    description: "Operational wrapper: fetch IMERG → winds → noise → precip → NetCDF ensemble.",
    files: ["STREAM-Sat-realtime/extension/"],
  },
  noise_gen: {
    id: "noise_gen",
    name: "Noise Generator",
    kind: "component",
    technology: "STREAM_NoiseGeneration.py",
    parent: "stream_sat",
    description: "Spatially correlated, non-stationary anisotropic noise from IMERG + winds.",
    files: ["STREAM-Sat-realtime/STREAM_NoiseGeneration.py"],
  },
  precip_sim: {
    id: "precip_sim",
    name: "Precipitation Simulator",
    kind: "component",
    technology: "STREAM_PrecipSimulation.py",
    parent: "stream_sat",
    description: "CSGD error model applied to IMERG, conditioned on noise → N-member ensemble.",
    files: ["STREAM-Sat-realtime/STREAM_PrecipSimulation.py"],
  },
  wind_adapter: {
    id: "wind_adapter",
    name: "GFS Wind Adapter",
    kind: "component",
    technology: "gfs_to_mv_adapter.py",
    parent: "stream_sat",
    description: "Downloads GFS winds, interpolates to 0.1°, converts U/V to speed/direction.",
    files: ["STREAM-Sat-realtime/extension/"],
  },
  state_persist: {
    id: "state_persist",
    name: "State Persistence",
    kind: "component",
    technology: "state_persistence.py",
    parent: "stream_sat",
    description: "Tracks last successful timestamp to avoid redundant downloads.",
    files: ["STREAM-Sat-realtime/extension/"],
  },
  nc2tif: {
    id: "nc2tif",
    name: "NetCDF → GeoTIFF",
    kind: "component",
    technology: "RainyDay scripts",
    parent: "stream_sat",
    description: "Converts ensemble NetCDF to per-member GeoTIFF stacks.",
  },

  // ── EF5 Job Builder components ──────────────────────────────────────
  prepare_ef5: {
    id: "prepare_ef5",
    name: "prepare_ef5()",
    kind: "component",
    technology: "ef5_routines.py",
    parent: "ef5_builder",
    description: "Builds one EF5 job: resolves window, locates states, fills template, stages precip.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },
  control_filler: {
    id: "control_filler",
    name: "Control File Filler",
    kind: "component",
    technology: "template substitution",
    parent: "ef5_builder",
    description: "Substitutes placeholders into EF5 control template → runnable control file.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },
  precip_stager: {
    id: "precip_stager",
    name: "Precip Stager",
    kind: "component",
    technology: "file copy",
    parent: "ef5_builder",
    description: "Copies relevant precip GeoTIFFs into the per-job staging folder.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },
  state_finder: {
    id: "state_finder",
    name: "State Finder",
    kind: "component",
    technology: "7-day lookback",
    parent: "ef5_builder",
    description: "Searches backward for a usable model state; cold-start fallback.",
    files: ["tito_utils/ef5/ef5_routines.py"],
  },

  // ── Neighbor elements (used in deeper views) ────────────────────────
  ef5_binary: {
    id: "ef5_binary",
    name: "EF5 Binary",
    kind: "container",
    technology: "C++ executable",
    description: "Compiled EF5 hydrologic model, invoked as a subprocess per job.",
  },
  imerg_store: {
    id: "imerg_store",
    name: "IMERG Early Store",
    kind: "containerDb",
    technology: "netCDF",
    description: "Hourly 0.1° IMERG Early QPE consumed by the STREAM-Sat engine.",
  },
  merra2_store: {
    id: "merra2_store",
    name: "MERRA2 Wind Store",
    kind: "containerDb",
    technology: "netCDF",
    description: "U850/V850 hourly winds used as offline motion vectors.",
  },
  csgd_model: {
    id: "csgd_model",
    name: "CSGD Error Model",
    kind: "containerDb",
    technology: "netCDF",
    description: "Pre-trained per-pixel CSGD error-distribution parameters.",
  },
  gfs_winds: {
    id: "gfs_winds",
    name: "GFS Wind Forecasts",
    kind: "containerDb",
    technology: "GRIB2 → netCDF",
    description: "Operational 850 hPa GFS winds for real-time motion vectors.",
  },
};

// ─────────────────────────────────────────────────────────────────────────
// RELATIONSHIPS
// ─────────────────────────────────────────────────────────────────────────

export const relationships: C4Rel[] = [
  // ── System Context ──────────────────────────────────────────────────
  { from: "operator", to: "tito", label: "Triggers forecast", technology: "cron / CLI" },
  { from: "tito", to: "nasa_gpm", label: "Downloads IMERG", technology: "HTTPS" },
  { from: "tito", to: "scampr", label: "Downloads SCaMPR", technology: "HTTPS" },
  { from: "tito", to: "noaa_gfs", label: "Downloads GFS", technology: "HTTPS" },
  { from: "tito", to: "arome", label: "Downloads AROME", technology: "HTTPS" },
  { from: "tito", to: "merra2", label: "Reads winds", technology: "HTTPS" },

  // ── Container level ─────────────────────────────────────────────────
  { from: "operator", to: "orchestrator", label: "Triggers forecast", technology: "cron" },
  { from: "operator", to: "config_store", label: "Edits config", technology: "text editor" },
  { from: "orchestrator", to: "config_store", label: "Reads config", technology: "importlib" },
  { from: "orchestrator", to: "qpe_pipeline", label: "Runs QPE", technology: "function call" },
  { from: "orchestrator", to: "qpf_pipeline", label: "Runs QPF", technology: "function call" },
  { from: "orchestrator", to: "ef5_builder", label: "Builds jobs", technology: "function call" },
  { from: "orchestrator", to: "ef5_runner", label: "Runs simulations", technology: "ThreadPool" },
  { from: "orchestrator", to: "state_mgr", label: "Manages states", technology: "function call" },
  { from: "qpe_pipeline", to: "nasa_gpm", label: "Downloads IMERG", technology: "HTTPS" },
  { from: "qpe_pipeline", to: "scampr", label: "Downloads SCaMPR", technology: "HTTPS" },
  { from: "qpe_pipeline", to: "file_store", label: "Writes QPE", technology: "File I/O" },
  { from: "qpf_pipeline", to: "noaa_gfs", label: "Downloads GFS", technology: "HTTPS" },
  { from: "qpf_pipeline", to: "arome", label: "Downloads AROME", technology: "HTTPS" },
  { from: "qpf_pipeline", to: "file_store", label: "Writes QPF", technology: "File I/O" },
  { from: "ef5_builder", to: "file_store", label: "Reads precip & templates", technology: "File I/O" },
  { from: "ef5_builder", to: "state_mgr", label: "Checks states", technology: "File scan" },
  { from: "ef5_runner", to: "file_store", label: "Writes outputs", technology: "File I/O" },
  { from: "state_mgr", to: "file_store", label: "Reads/writes states", technology: "File I/O" },

  // ── QPE Pipeline sub-modules ────────────────────────────────────────
  { from: "imerg_src", to: "nasa_gpm", label: "Downloads IMERG", technology: "HTTPS" },
  { from: "scampr_src", to: "scampr", label: "Downloads SCaMPR", technology: "HTTPS" },
  { from: "stream_sat", to: "nasa_gpm", label: "Reads IMERG", technology: "HTTPS" },
  { from: "stream_sat", to: "merra2", label: "Reads winds", technology: "HTTPS" },
  { from: "imerg_src", to: "file_store", label: "Writes GeoTIFFs", technology: "File I/O" },
  { from: "scampr_src", to: "file_store", label: "Writes GeoTIFFs", technology: "File I/O" },
  { from: "stream_sat", to: "file_store", label: "Writes ensembles", technology: "File I/O" },

  // ── QPF Pipeline sub-modules ────────────────────────────────────────
  { from: "gfs_src", to: "noaa_gfs", label: "Downloads GFS", technology: "HTTPS" },
  { from: "arome_src", to: "arome", label: "Downloads AROME", technology: "HTTPS" },
  { from: "gfs_src", to: "file_store", label: "Writes GeoTIFFs", technology: "File I/O" },
  { from: "arome_src", to: "file_store", label: "Writes GeoTIFFs", technology: "File I/O" },

  // ── Orchestrator components ─────────────────────────────────────────
  { from: "main_ctl", to: "config_store", label: "Loads config", technology: "importlib" },
  { from: "main_ctl", to: "qpe_pipeline", label: "Runs QPE", technology: "function call" },
  { from: "main_ctl", to: "qpf_pipeline", label: "Runs QPF", technology: "function call" },
  { from: "main_ctl", to: "ef5_exec", label: "Runs EF5", technology: "function call" },
  { from: "main_ctl", to: "state_comp", label: "Finds states", technology: "function call" },
  { from: "ef5_exec", to: "ef5_binary", label: "Invokes", technology: "subprocess" },
  { from: "ef5_exec", to: "file_store", label: "Writes outputs", technology: "File I/O" },
  { from: "state_comp", to: "file_store", label: "Scans states (7-day)", technology: "File scan" },

  // ── STREAM-Sat components ───────────────────────────────────────────
  { from: "rt_pipeline", to: "imerg_store", label: "Fetches IMERG", technology: "HTTPS" },
  { from: "rt_pipeline", to: "gfs_winds", label: "Downloads winds", technology: "HTTPS" },
  { from: "rt_pipeline", to: "wind_adapter", label: "Adapts winds", technology: "function call" },
  { from: "rt_pipeline", to: "state_persist", label: "Pipeline state", technology: "JSON" },
  { from: "rt_pipeline", to: "noise_gen", label: "Generates noise", technology: "function call" },
  { from: "rt_pipeline", to: "precip_sim", label: "Simulates precip", technology: "function call" },
  { from: "rt_pipeline", to: "nc2tif", label: "Converts", technology: "subprocess" },
  { from: "noise_gen", to: "merra2_store", label: "Reads winds", technology: "netCDF" },
  { from: "noise_gen", to: "gfs_winds", label: "Reads winds", technology: "netCDF" },
  { from: "precip_sim", to: "csgd_model", label: "Reads params", technology: "netCDF" },
  { from: "precip_sim", to: "imerg_store", label: "Reads IMERG", technology: "netCDF" },

  // ── EF5 Job Builder components ──────────────────────────────────────
  { from: "prepare_ef5", to: "state_finder", label: "Locates state", technology: "function call" },
  { from: "prepare_ef5", to: "control_filler", label: "Fills template", technology: "function call" },
  { from: "prepare_ef5", to: "precip_stager", label: "Stages precip", technology: "function call" },
  { from: "control_filler", to: "file_store", label: "Reads templates", technology: "File I/O" },
  { from: "precip_stager", to: "file_store", label: "Copies precip", technology: "file copy" },
  { from: "state_finder", to: "file_store", label: "Scans states", technology: "File scan" },
];

// ─────────────────────────────────────────────────────────────────────────
// VIEW DERIVATION
// ─────────────────────────────────────────────────────────────────────────

const CONTEXT_IDS = ["operator", "tito", "nasa_gpm", "scampr", "noaa_gfs", "arome", "merra2"];

function relsWithin(ids: Set<string>): C4Rel[] {
  return relationships.filter((r) => ids.has(r.from) && ids.has(r.to));
}

export function contextView(): C4View {
  const ids = new Set(CONTEXT_IDS);
  return {
    id: "context",
    title: "TITO — System Context",
    subtitle: "Level 1 · Operator, external data sources, and the TITO platform",
    rootId: null,
    boundaryIds: ["tito"],
    externalIds: CONTEXT_IDS.filter((id) => id !== "tito"),
    rels: relsWithin(ids),
  };
}

export function elementView(rootId: string): C4View {
  const root = elements[rootId];
  if (!root?.children?.length) return contextView();

  const boundaryIds = root.children;
  const boundarySet = new Set(boundaryIds);

  const externalSet = new Set<string>();
  for (const r of relationships) {
    const fi = boundarySet.has(r.from);
    const ti = boundarySet.has(r.to);
    if (fi && !ti && elements[r.to]) externalSet.add(r.to);
    if (ti && !fi && elements[r.from]) externalSet.add(r.from);
  }

  const allIds = new Set([...boundaryIds, ...externalSet]);
  const levelNum = 2 + ancestors(rootId).length;

  return {
    id: rootId,
    title: `${root.name} — ${root.childLabel ?? "Components"}`,
    subtitle: `Level ${levelNum} · ${root.technology ?? root.kind}`,
    rootId,
    boundaryIds,
    externalIds: [...externalSet],
    rels: relsWithin(allIds),
  };
}

export function hasChildren(id: string): boolean {
  return !!elements[id]?.children?.length;
}

export function ancestors(id: string): string[] {
  const chain: string[] = [];
  let cur = elements[id]?.parent;
  while (cur) {
    chain.unshift(cur);
    cur = elements[cur]?.parent;
  }
  return chain;
}
