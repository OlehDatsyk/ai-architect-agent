import type { InterpretationResult } from "../types/design";

export function healthBody(configured = true, blender: "found" | "not_configured" = "not_configured") {
  return {
    status: "ok", service: "AI Architect Agent", version: "0.1.0", environment: "test",
    timestamp: "2026-10-02T12:00:00Z",
    checks: {
      anthropic: { configured, model: "claude-sonnet-5-5", verification: { status: "not_checked", structured_outputs: "not_checked", code: null, message: null, checked_at: null } },
      blender: { status: blender, detail: "" },
    },
  };
}

export const interpretation: InterpretationResult = {
  intent: {
    understood: true,
    project_name: "Contemporary British Family House",
    summary: "A two-storey family house with an integral garage.",
    building_type: "detached_house",
    style: "contemporary",
    floors: 2,
    floor_height: 2.7,
    footprint_width: 9.6,
    footprint_depth: 8.5,
    entrance_room: "hall",
    rooms: [
      { id: "hall", name: "Entrance Hall", type: "entrance", floor: 0, target_area: 10, glazing: "standard", preferred_side: "front" },
      { id: "garage", name: "Garage", type: "garage", floor: 0, target_area: 18, glazing: "none", preferred_side: "front" },
      { id: "landing", name: "Landing", type: "landing", floor: 1, target_area: 12, glazing: "standard", preferred_side: "any" },
      { id: "bedroom_1", name: "Master Bedroom", type: "bedroom", floor: 1, target_area: 16, glazing: "standard", preferred_side: "front" },
      { id: "ensuite", name: "En-suite", type: "ensuite", floor: 1, target_area: 4, glazing: "standard", preferred_side: "any" },
    ],
    connections: [],
    stairs: [{ from_floor: 0, to_floor: 1, start_room: "hall", arrival_room: "landing" }],
    roof: { type: "gable", pitch: 35, material: "slate" },
    exterior: { wall_material: "brick", accent_material: null, window_frame_material: "dark_metal" },
    site: { driveway: true, patio: true, balcony_rooms: [] },
    assumptions: ["Assumed the second bathroom is an en-suite."],
  },
  report: {
    status: "WARNING", error_count: 0, warning_count: 1,
    issues: [{ severity: "warning", code: "floor_underfilled", message: "Rooms on floor 0 total 28 m² of a 82 m² footprint; they will be enlarged to fill it.", element_ids: [], location: null }],
    fixes: [],
  },
  constraints_applied: ["Style set to contemporary as requested (Claude proposed modern)."],
  attempts: 1,
  model: "claude-sonnet-5-5",
  usage: { input_tokens: 3000, output_tokens: 1500, cache_read_input_tokens: 0 },
  completed_stages: ["understanding_request"],
};

import type { PlanResponse } from "../types/design";

const svg = (name: string) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><text>${name}</text><script>alert(1)</script></svg>`;

export const planResponse: PlanResponse = {
  specification: {},
  report: {
    status: "WARNING", error_count: 0, warning_count: 1,
    issues: [{ severity: "warning", code: "room_small", message: "En-suite is 2.9 m², below the typical minimum of 3.0 m².", element_ids: [], location: null }],
    fixes: [],
  },
  summary: {
    project_name: "Contemporary British Family House", floors: 2, width: 9.6, depth: 8.5, total_height: 8.28,
    gross_floor_area: 163.2, bedrooms: 3, bathrooms: 2, wcs: 1, garage: "single", roof_type: "gable",
  },
  notes: ["Merged Upper Corridor into Landing; the plan uses one circulation space per floor."],
  plans: [
    { level: 0, name: "Ground floor", svg: svg("Ground") },
    { level: 1, name: "First floor", svg: svg("First") },
  ],
  completed_stages: ["planning_rooms", "creating_specification", "validating_design"],
};
