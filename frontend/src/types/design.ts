// Mirrors backend/app/models/intent.py and app/agents/architect_agent.py.

export type Glazing = "none" | "standard" | "large" | "floor_to_ceiling";
export type GarageSize = "none" | "single" | "double";
export type RoofChoice = "automatic" | "flat" | "gable" | "hip" | "shed";
export type DetailLevel = "concept" | "standard" | "detailed";

export interface DesignConstraints {
  building_type?: string;
  style?: string;
  floors?: number;
  width?: number;
  depth?: number;
  height?: number;
  bedrooms?: number;
  bathrooms?: number;
  garage?: GarageSize;
  roof?: RoofChoice;
  detail_level?: DetailLevel;
}

export interface DesignRequest {
  prompt: string;
  constraints: DesignConstraints;
}

export interface IntentRoom {
  id: string;
  name: string;
  type: string;
  floor: number;
  target_area: number;
  glazing: Glazing;
  preferred_side: "front" | "rear" | "left" | "right" | "any";
}

export interface DesignIntent {
  understood: boolean;
  project_name: string;
  summary: string;
  building_type: string;
  style: string;
  floors: number;
  floor_height: number;
  footprint_width: number;
  footprint_depth: number;
  entrance_room: string;
  rooms: IntentRoom[];
  connections: { room_a: string; room_b: string; kind: "door" | "open" }[];
  stairs: { from_floor: number; to_floor: number; start_room: string; arrival_room: string }[];
  roof: { type: string; pitch: number; material: string };
  exterior: { wall_material: string; accent_material: string | null; window_frame_material: string };
  site: { driveway: boolean; patio: boolean; balcony_rooms: string[] };
  assumptions: string[];
}

export interface ValidationIssue {
  severity: "warning" | "error";
  code: string;
  message: string;
  element_ids: string[];
  location: string | null;
}

export interface ValidationReport {
  status: "PASS" | "WARNING" | "ERROR";
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
  fixes: { code: string; message: string; element_ids: string[] }[];
}

export interface InterpretationResult {
  intent: DesignIntent;
  report: ValidationReport;
  constraints_applied: string[];
  attempts: number;
  model: string;
  usage: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number };
  completed_stages: string[];
}

export interface FloorPlanPreview {
  level: number;
  name: string;
  svg: string;
}

export interface SpecificationSummary {
  project_name: string;
  floors: number;
  width: number;
  depth: number;
  total_height: number;
  gross_floor_area: number;
  bedrooms: number;
  bathrooms: number;
  wcs: number;
  garage: GarageSize;
  roof_type: string;
}

export interface PlanResponse {
  /** The full BuildingSpecification; typed loosely until the frontend needs its fields. */
  specification: Record<string, unknown>;
  report: ValidationReport;
  summary: SpecificationSummary;
  notes: string[];
  plans: FloorPlanPreview[];
  completed_stages: string[];
}

export interface CameraInfo {
  name: string;
  role: string;
}

export interface BuildResponse {
  job_id: string;
  blend_url: string;
  cameras: CameraInfo[];
  blender_version: string;
  object_count: number;
  duration_seconds: number;
  completed_stages: string[];
}

export type RenderQuality = "preview" | "standard" | "high";
export type RenderResolution = "1280x720" | "1920x1080" | "2560x1440";
export type RenderEngine = "auto" | "eevee" | "cycles";

export interface RenderRequest {
  camera: string;
  preset: "day" | "evening";
  quality: RenderQuality;
  resolution: RenderResolution;
  engine: RenderEngine;
}

export interface RenderResponse {
  render_id: string;
  image_url: string;
  camera: string;
  role: string | null;
  preset: string;
  quality: string;
  engine: string;
  width: number;
  height: number;
  duration_seconds: number;
  note: string | null;
  completed_stages: string[];
}

export interface Override {
  op: string;
  params: Record<string, string>;
}

export interface ModifyResponse extends Omit<PlanResponse, "completed_stages"> {
  intent: DesignIntent;
  overrides: Override[];
  change_summary: string;
  changes: string[];
  assumptions: string[];
  attempts: number;
  model: string;
  completed_stages: string[];
}

export interface ModificationRecord {
  request: string;
  summary: string;
  changes: string[];
  assumptions: string[];
}

export interface ProjectListItem {
  id: string;
  name: string;
  version: number;
  updated_at: string;
  floors: number;
  bedrooms: number;
  changes: number;
  thumbnail_url: string | null;
}

export interface SavedBuildInfo {
  job_id: string;
  blender_version: string;
  object_count: number;
  cameras: CameraInfo[];
  blend_url: string;
  blend_path: string;
  available: boolean;
}

export interface SavedRenderInfo {
  render_id: string;
  job_id: string;
  camera: string;
  preset: "day" | "evening";
  quality: RenderQuality;
  engine: "eevee" | "cycles";
  width: number;
  height: number;
  note: string | null;
  image_url: string;
  image_path: string;
  available: boolean;
}

export interface ProjectView {
  id: string;
  version: number;
  name: string;
  updated_at: string;
  brief: string;
  constraints: DesignConstraints;
  interpretation: InterpretationResult;
  intent: DesignIntent;
  overrides: Override[];
  specification: Record<string, unknown>;
  report: ValidationReport;
  notes: string[];
  history: ModificationRecord[];
  build: SavedBuildInfo | null;
  renders: SavedRenderInfo[];
  summary: SpecificationSummary;
  plans: FloorPlanPreview[];
}

export interface ProjectPayload {
  name: string;
  brief: string;
  constraints: DesignConstraints;
  interpretation: InterpretationResult;
  intent: DesignIntent;
  overrides: Override[];
  specification: Record<string, unknown>;
  notes: string[];
  history: ModificationRecord[];
  build: { job_id: string; blender_version: string; object_count: number; cameras: CameraInfo[] } | null;
  renders: Omit<SavedRenderInfo, "image_url" | "image_path" | "available">[];
}
