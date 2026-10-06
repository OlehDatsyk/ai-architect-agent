export const PIPELINE_STAGES: readonly { id: string; text: string }[] = [
  { id: "understanding_request", text: "Understanding request" },
  { id: "creating_specification", text: "Creating architectural specification" },
  { id: "validating_design", text: "Validating design" },
  { id: "planning_rooms", text: "Planning rooms" },
  { id: "preparing_scene", text: "Preparing Blender scene" },
  { id: "generating_geometry", text: "Generating geometry" },
  { id: "applying_materials", text: "Applying materials" },
  { id: "creating_lighting", text: "Creating lighting" },
  { id: "creating_cameras", text: "Creating cameras" },
  { id: "rendering", text: "Rendering" },
];

export type StageStatus = "not_started" | "in_progress" | "complete" | "failed";

const STATUS_TEXT: Record<StageStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
  failed: "Failed",
};

const STATUS_CLASS: Record<StageStatus, string> = {
  not_started: "text-muted",
  in_progress: "font-medium text-ink",
  complete: "font-medium text-ok",
  failed: "font-medium text-revision",
};

/** Stage list. A stage only changes when the backend reports it, or while its request is in flight. */
export function PipelineStages({ statuses = {} }: { statuses?: Partial<Record<string, StageStatus>> }) {
  return (
    <section aria-labelledby="pipeline-heading" className="flex flex-col gap-2">
      <h2 id="pipeline-heading" className="text-[17px] font-semibold">Generation stages</h2>
      <ol className="flex flex-col">
        {PIPELINE_STAGES.map((stage, i) => {
          const status = statuses[stage.id] ?? "not_started";
          return (
            <li key={stage.id} className="flex items-baseline gap-3 border-b border-line py-1.5 text-[13px] last:border-b-0">
              <span className="w-5 shrink-0 text-right tabular-nums text-muted">{i + 1}</span>
              <span className="flex-1">{stage.text}</span>
              <span className={STATUS_CLASS[status]}>{STATUS_TEXT[status]}</span>
            </li>
          );
        })}
      </ol>
      <p className="text-[13px] leading-relaxed text-muted">
        Stages update from the backend as each one finishes.
      </p>
    </section>
  );
}
