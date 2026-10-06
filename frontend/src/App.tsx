import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { BrandMark } from "./components/BrandMark";
import { DesignReview } from "./components/DesignReview";
import { PipelineStages, type StageStatus } from "./components/PipelineStages";
import { PlanSheet, type SheetState } from "./components/PlanSheet";
import { ProjectsPanel } from "./components/ProjectsPanel";
import { PromptPanel } from "./components/PromptPanel";
import { SaveBar } from "./components/SaveBar";
import { SystemStatus } from "./components/SystemStatus";
import { type BuildState, useBuild } from "./hooks/useBuild";
import { DEFAULT_RENDER, type RenderState, useRenders } from "./hooks/useRenders";
import { useHealth } from "./hooks/useHealth";
import { signature, useProjects } from "./hooks/useProjects";
import { getProject } from "./services/api";
import { type InterpretationState, useInterpretation } from "./hooks/useInterpretation";
import type { BuildResponse, DesignConstraints, ProjectPayload, ProjectView, RenderResponse } from "./types/design";

const BUILT_STAGES = ["preparing_scene", "applying_materials", "generating_geometry", "creating_lighting", "creating_cameras"];

function payloadFrom(name: string, brief: string, constraints: DesignConstraints, interpretation: InterpretationState,
                     build: BuildState, renders: RenderResponse[]): ProjectPayload | null {
  if (interpretation.kind !== "success" || !interpretation.plan) return null;
  const built = build.kind === "success" ? build.result : null;
  return {
    name: name.trim() || interpretation.result.intent.project_name, brief, constraints,
    interpretation: interpretation.result, intent: interpretation.result.intent, overrides: interpretation.overrides,
    specification: interpretation.plan.specification, notes: interpretation.plan.notes, history: interpretation.history,
    build: built ? { job_id: built.job_id, blender_version: built.blender_version, object_count: built.object_count, cameras: built.cameras } : null,
    renders: built ? renders.filter((r) => r.image_url.includes(built.job_id)).map((r) => ({
      render_id: r.render_id, job_id: built.job_id, camera: r.camera, preset: r.preset as "day" | "evening",
      quality: r.quality as "preview" | "standard" | "high", engine: r.engine as "eevee" | "cycles", width: r.width, height: r.height, note: r.note,
    })) : [],
  };
}

function restoredState(project: ProjectView): Extract<InterpretationState, { kind: "success" }> {
  return {
    kind: "success",
    result: { ...project.interpretation, intent: project.intent },
    plan: { specification: project.specification, report: project.report, summary: project.summary, notes: project.notes,
            plans: project.plans, completed_stages: ["planning_rooms", "creating_specification", "validating_design"] },
    planError: null, overrides: project.overrides, history: project.history, modifying: false, modifyError: null,
  };
}

function restoredBuild(project: ProjectView): BuildResponse | null {
  const b = project.build;
  return b && b.available ? { job_id: b.job_id, blend_url: b.blend_url, cameras: b.cameras, blender_version: b.blender_version,
                              object_count: b.object_count, duration_seconds: 0, completed_stages: BUILT_STAGES } : null;
}

function restoredRenders(project: ProjectView): RenderResponse[] {
  return project.renders.filter((r) => r.available).map((r) => ({
    render_id: r.render_id, image_url: r.image_url, camera: r.camera, role: null, preset: r.preset, quality: r.quality,
    engine: r.engine, width: r.width, height: r.height, duration_seconds: 0, note: r.note, completed_stages: ["rendering"],
  })).reverse();
}

const PLANNING_STAGES = ["planning_rooms", "creating_specification", "validating_design"] as const;

const BUILD_STAGES = ["preparing_scene", "applying_materials", "generating_geometry", "creating_lighting", "creating_cameras"] as const;

function buildStatuses(build: BuildState): Partial<Record<string, StageStatus>> {
  const all = (ids: readonly string[], status: StageStatus) => Object.fromEntries(ids.map((id) => [id, status]));
  if (build.kind === "building") return all(BUILD_STAGES, "in_progress");
  if (build.kind === "success") return all(build.result.completed_stages, "complete");
  if (build.kind === "error") return { preparing_scene: "failed" };
  return {};
}

function renderStatuses(renders: RenderState): Partial<Record<string, StageStatus>> {
  if (renders.busy) return { rendering: "in_progress" };
  if (renders.error && renders.renders.length === 0) return { rendering: "failed" };
  return renders.renders.length > 0 ? { rendering: "complete" } : {};
}

function stageStatuses(state: InterpretationState): Partial<Record<string, StageStatus>> {
  const all = (ids: readonly string[], status: StageStatus) => Object.fromEntries(ids.map((id) => [id, status]));
  switch (state.kind) {
    case "loading":
      return { understanding_request: "in_progress" };
    case "error":
      return { understanding_request: "failed" };
    case "planning":
      return { ...all(state.result.completed_stages, "complete"), ...all(PLANNING_STAGES, "in_progress") };
    case "success":
      return {
        ...all(state.result.completed_stages, "complete"),
        ...(state.plan ? all(state.plan.completed_stages, "complete") : {}),
        ...(state.planError ? { planning_rooms: "failed" as const } : {}),
      };
    default:
      return {};
  }
}

export default function App() {
  const { state: health, retry: retryHealth } = useHealth();
  const { state: interpretation, interpret, modify, cancel, restore: restoreInterpretation } = useInterpretation();
  const { state: build, build: buildInBlender, reset: resetBuild, restore: restoreBuild } = useBuild();
  const { state: renders, render, reset: resetRenders, restore: restoreRenders } = useRenders();
  const projects = useProjects();
  const [projectName, setProjectName] = useState("");
  const [submitted, setSubmitted] = useState<{ brief: string; constraints: DesignConstraints }>({ brief: "", constraints: {} });
  const jobId = build.kind === "success" ? build.result.job_id : null;
  const restoredJobRef = useRef<string | null>(null);
  // The project name starts as the design's name, once per new brief; after that it is the user's.
  const nameSeededFor = useRef<object | null>(null);
  useEffect(() => {
    if (interpretation.kind === "success" && nameSeededFor.current !== submitted) {
      nameSeededFor.current = submitted;
      setProjectName(interpretation.result.intent.project_name);
    }
  }, [interpretation, submitted]);

  // Every new build gets a preview render straight away (front view, day, preview quality),
  // except a build reopened from a saved project, whose renders are restored instead.
  useEffect(() => {
    if (jobId && jobId !== restoredJobRef.current) void render(jobId, DEFAULT_RENDER);
  }, [jobId, render]);

  const payload = useMemo(
    () => payloadFrom(projectName, submitted.brief, submitted.constraints, interpretation, build, renders.renders),
    [projectName, submitted, interpretation, build, renders.renders],
  );
  const saveStatus = !projects.current ? "new" : signature(payload) === projects.current.savedSignature ? "saved" : "unsaved";

  const openProject = useCallback(async (id: string) => {
    try {
      const project = await getProject(id);
      const state = restoredState(project);
      const builtResult = restoredBuild(project);
      const restoredRenderList = restoredRenders(project);
      restoredJobRef.current = builtResult?.job_id ?? null;
      setPrompt(project.brief);
      setConstraints(Object.fromEntries(Object.entries(project.constraints).filter(([, v]) => v !== null && v !== undefined)) as DesignConstraints);
      const opened = { brief: project.brief, constraints: project.constraints };
      nameSeededFor.current = opened;  // keep the saved name rather than the design's default
      setSubmitted(opened);
      setProjectName(project.name);
      restoreInterpretation(state);
      restoreBuild(builtResult);
      restoreRenders(restoredRenderList);
      projects.opened(project, payloadFrom(project.name, project.brief, project.constraints, state,
        builtResult ? { kind: "success", result: builtResult } : { kind: "idle" }, restoredRenderList)!);
    } catch {
      // The projects hook shows load errors on its next action; keep the current design untouched.
    }
  }, [projects, restoreInterpretation, restoreBuild, restoreRenders]);
  const [prompt, setPrompt] = useState("");
  const [constraints, setConstraints] = useState<DesignConstraints>({});
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const unavailableReason =
    health.kind === "error"
      ? "The backend is not reachable, so designs can't be generated yet."
      : health.kind === "ready" && !health.data.checks.anthropic.configured
      ? "Add ANTHROPIC_API_KEY to .env and restart the backend to generate designs."
      : null;

  const generate = () => {
    resetBuild();
    resetRenders();
    projects.forget();  // a new brief starts a new, unsaved project
    setProjectName("");
    setSubmitted({ brief: prompt.trim(), constraints });
    void interpret({ prompt: prompt.trim(), constraints });
  };

  const plan = interpretation.kind === "success" ? interpretation.plan : null;
  const blender = health.kind === "ready" ? health.data.checks.blender.status : null;
  const buildUnavailableReason = !plan
    ? "A floor plan is needed before the design can be built."
    : blender !== "found"
    ? "Set BLENDER_EXECUTABLE in .env and restart the backend to build designs in Blender."
    : null;

  const focusBrief = () => {
    textareaRef.current?.focus();
    textareaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const sheet: SheetState =
    interpretation.kind === "loading"
      ? { kind: "loading", onCancel: cancel }
      : interpretation.kind === "error"
      ? { kind: "error", message: interpretation.message, issues: interpretation.issues, onRetry: generate }
      : { kind: "empty" };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-ink/70 bg-surface px-5 py-3">
        <div className="flex items-center gap-2.5">
          <BrandMark className="size-6 text-ink" />
          <h1 className="text-[17px] font-semibold tracking-tight [font-stretch:115%]">AI Architect Agent</h1>
        </div>
        <p className="hidden text-[13px] text-muted sm:block">Concept designs, not regulation-checked plans</p>
      </header>

      <main className="grid flex-1 grid-cols-[minmax(0,1fr)] gap-px bg-line lg:grid-cols-[22rem_minmax(0,1fr)_20rem]">
        <div className="bg-canvas p-5">
          <PromptPanel
            prompt={prompt}
            onPromptChange={setPrompt}
            constraints={constraints}
            onConstraintsChange={setConstraints}
            onGenerate={generate}
            busy={interpretation.kind === "loading" || interpretation.kind === "planning"}
            unavailableReason={unavailableReason}
            textareaRef={textareaRef}
          />
          <div className="mt-6">
            <ProjectsPanel projects={projects.projects} currentId={projects.current?.id ?? null}
              disabled={interpretation.kind === "loading" || interpretation.kind === "planning"}
              onOpen={(id) => void openProject(id)} onDelete={(id) => void projects.remove(id)} />
          </div>
        </div>
        <div className="flex min-w-0 bg-canvas p-5">
          {interpretation.kind === "success" || interpretation.kind === "planning" ? (
            <DesignReview
              result={interpretation.result}
              plan={interpretation.kind === "success" ? interpretation.plan : null}
              planning={interpretation.kind === "planning"}
              planError={interpretation.kind === "success" ? interpretation.planError : null}
              onModify={focusBrief}
              build={build}
              buildUnavailableReason={buildUnavailableReason}
              onApprove={() => {
                resetRenders();
                if (plan) void buildInBlender(plan.specification);
              }}
              renders={renders}
              onRender={(request) => jobId && void render(jobId, request)}
              history={interpretation.kind === "success" ? interpretation.history : []}
              modifying={interpretation.kind === "success" && interpretation.modifying}
              modifyError={interpretation.kind === "success" ? interpretation.modifyError : null}
              modifyUnavailableReason={unavailableReason && unavailableReason.replace("to generate designs", "to change designs")}
              saveBar={
                <SaveBar
                  name={projectName}
                  onNameChange={setProjectName}
                  status={saveStatus}
                  saving={projects.busy}
                  error={projects.error}
                  onSave={() => payload && void projects.save(payload)}
                />
              }
              onChange={async (request) => {
                const changed = await modify(request);
                if (changed) {
                  resetBuild(); // the model no longer matches the design: build again to see the change
                  resetRenders();
                }
                return changed;
              }}
            />
          ) : (
            <PlanSheet state={sheet} />
          )}
        </div>
        <aside className="flex flex-col gap-8 bg-canvas p-5">
          <SystemStatus state={health} onRetry={retryHealth} />
          <PipelineStages statuses={{ ...stageStatuses(interpretation), ...buildStatuses(build), ...renderStatuses(renders) }} />
        </aside>
      </main>
    </div>
  );
}
