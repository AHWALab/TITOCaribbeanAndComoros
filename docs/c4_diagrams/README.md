# TITO — C4 Architecture Diagrams

This directory contains the **C4 model** architecture diagrams for the **TITO (Threading Inputs to Outputs)** operational hydrologic forecasting framework, including the **STREAM-Sat** ensemble precipitation pipeline.

All diagrams are written in **PlantUML** (.puml) and use the official [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) standard library.

---

## Diagrams Overview

| #   | Diagram                                                         | C4 Level       | Description                                                                                    |
| --- | --------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------- |
| 01  | [System Context](#01-system-context)                            | **Level 1**    | TITO in its environment — users, external data sources, and downstream systems                 |
| 02  | [Container Diagram](#02-container-diagram)                      | **Level 2**    | TITO's internal containers: Orchestrator, STREAM-Sat, EF5 Builder, Runner, State Manager, etc. |
| 03  | [Component: Orchestrator](#03-component-orchestrator)           | **Level 3**    | Internal components of the Orchestrator — cycle manager, job builders, execution engine        |
| 04  | [Component: STREAM-Sat](#04-component-stream-sat)               | **Level 3**    | STREAM-Sat internals — noise generation, precipitation simulation, real-time pipeline          |
| 05  | [Dynamic: Simulation Timeline](#05-dynamic-simulation-timeline) | **Dynamic**    | End-to-end sequence of a single hourly cycle (Nowcast mode)                                    |
| 06  | [Dynamic: State Management](#06-dynamic-state-management)       | **Dynamic**    | Cold start, warm start, ensemble isolation, and hindcast state chaining                        |
| 07  | [Deployment](#07-deployment)                                    | **Deployment** | Physical deployment — compute nodes, storage, external services, cron                          |
| 08  | [System Landscape](#08-system-landscape)                        | **Landscape**  | WMO Caribbean & Comoros project-wide system landscape                                          |

---

## How to Render

> **Important:** These diagrams use PlantUML's **built-in C4 standard library** (`!include <C4/C4_Container>`).
> This requires **PlantUML ≥ v1.2024.0**. The library is bundled with PlantUML — no external downloads needed.

### Option 1: PlantUML Online Server

Go to [https://www.plantuml.com/plantuml/uml/](https://www.plantuml.com/plantuml/uml/) and paste the .puml content.

### Option 2: VS Code Extension

Install the **PlantUML** extension (`jebbs.plantuml`), open any `.puml` file, and press `Alt+D` to preview.

### Option 3: Local PlantUML JAR

```bash
java -jar plantuml.jar -tpng docs/c4_diagrams/*.puml
```

### Option 4: Python (plantuml)

```bash
pip install plantuml
python -m plantuml docs/c4_diagrams/
```

---

## Key Architecture Concepts

### TITO Operational Modes

| Mode                    | Trigger                              | Description                                              |
| ----------------------- | ------------------------------------ | -------------------------------------------------------- |
| **Nowcast**             | Cron (hourly @ HH:07)                | Real-time: downloads latest data, runs EF5, sends alerts |
| **Hindcast**            | CLI (`hindcast_manager.py`)          | Historical: steps through date range, chains states      |
| **STREAM-Sat Ensemble** | Config (`qpe_source = "STREAM_SAT"`) | 50-member ensemble QPE → EF5 per member                  |

### Precipitation Sources

| Source          | Type            | Latency        | Resolution     | Usage                     |
| --------------- | --------------- | -------------- | -------------- | ------------------------- |
| **IMERG Early** | Satellite QPE   | ~4 hours       | 0.1°, 30-min   | Primary QPE (T−4h window) |
| **SCaMPR**      | IR gap-fill QPE | ~30 min        | 0.1°, 30-min   | Gap fill T−4h → T         |
| **STREAM-Sat**  | Ensemble QPE    | ~4 hours       | 0.1°, 30-min   | 50-member ensemble        |
| **H-SAF H40B**  | Satellite QPE   | ~20 min        | 0.1°, 10-min   | Alternative QPE           |
| **GFS**         | NWP QPF         | 0–24h forecast | 0.25°, hourly  | QPF + wind vectors        |
| **AROME**       | Regional NWP    | 0–24h forecast | 2.5 km, hourly | High-res QPF              |

### EF5 Job Types (per cycle)

1. **IMERG-only** (QPE: T−10h → T−4h) — Saves state at T−4h
2. **SCaMPR + QPF** (QPE: T−4h → T, QPF: T → T+24h) — Uses IMERG state
3. **STREAM-Sat Phase A** (per member) — STREAM-Sat QPE only, saves state
4. **STREAM-Sat Phase B** (per member × QPF) — SCaMPR gap fill + QPF forecast
5. **Hindcast QPF** (per member) — QPF-only from STREAM-Sat state

### State Management

- **Warm Start**: Finds prior states via 7-day backward search → resumes from last state
- **Cold Start**: No states found → 6-hour warmup spin-up → saves state at cycle end
- **State Isolation**: STREAM-Sat ensemble members have separate state directories (`states/stream_sat/ensS{N}/<region>/`)
- **Hindcast Chaining**: Each cycle saves states → next cycle finds them automatically

### File: `orchestrator.py`

```
main()
  ├── Load config (importlib)
  ├── Determine cycle time (nowcast vs hindcast)
  └── _run_single_cycle()
        ├── STEP 1: prepare_all_precip()       — Download forcing
        ├── STEP 2: Build region_configs        — Timeline offsets
        ├── STEP 3: Create per-region dirs      — states, data, qpf_store
        ├── STEP 4: Stage QPF to regions        — File copy
        ├── STEP 5: Build & run EF5 jobs        — Core execution
        │     ├── STREAM-Sat Phase A (ensemble QPE)
        │     ├── STREAM-Sat Phase B (gap fill + QPF)
        │     ├── IMERG-only (QPE, save state)
        │     └── LR/SCaMPR+QPF (gap fill + QPF)
        └── STEP 6: Cleanup + summary + alerts
```

---

## References

- [C4 Model](https://c4model.com/) — Official C4 model website
- [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML) — PlantUML macros for C4
- [PlantUML](https://plantuml.com/) — Diagram-as-code tool
- [TITO Repository](https://github.com/AHWALab/TITOWA_1km) — Source code
- [EF5 Builder Toolkit](https://github.com/AHWALab/EF5-builder-toolkit) — GIS pre-processing
- [STREAM-Sat Paper](https://doi.org/10.1029/2021WR031650) — Hartke et al. (2022)
- [CSGD Error Model](https://github.com/KaidiWisc/CSGD_error_model) — Li et al. (2023)
