import type { ReactNode } from "react";

import type { BuildState } from "../hooks/useBuild";
import type { RenderState } from "../hooks/useRenders";
import type { PlanFailure } from "../hooks/useInterpretation";
import type { InterpretationResult, ModificationRecord, PlanResponse, RenderRequest } from "../types/design";
import { floorName, label, metres } from "../utils/labels";
import { FloorPlans } from "./FloorPlans";
import { ModifyPanel } from "./ModifyPanel";
import { ValidationPanel } from "./ValidationPanel";
import { RenderPanel } from "./RenderPanel";

interface Props {
  result: InterpretationResult;
  /** null while planning is in progress or if it failed */
  plan: PlanResponse | null;
  planning: boolean;
  planError: PlanFailure | null;
  onModify: () => void;
  build: BuildState;
  /** Why the design can't be sent to Blender yet, if it can't. */
  buildUnavailableReason: string | null;
  onApprove: () => void;
  renders: RenderState;
  onRender: (request: RenderRequest) => void;
  history: ModificationRecord[];
  modifying: boolean;
  modifyError: string | null;
  modifyUnavailableReason: string | null;
  onChange: (request: string) => Promise<boolean>;
  /** Save controls, shown under the summary. */
  saveBar?: ReactNode;
}

const GLAZING_TEXT: Record<string, string> = {
  none: "No windows",
  standard: "Windows",
  large: "Large windows",
  floor_to_ceiling: "Floor-to-ceiling glazing",
};

/** Shows what Claude understood, for the user to check before anything is built. */
export function DesignReview({
  result, plan, planning, planError, onModify, build, buildUnavailableReason, onApprove, renders, onRender,
  history, modifying, modifyError, modifyUnavailableReason, onChange, saveBar,
}: Props) {
  const { intent, report } = result;
  const count = (type: string) => intent.rooms.filter((r) => r.type === type).length;
  const garages = intent.rooms.filter((r) => r.type === "garage");
  const garage = garages.length === 0 ? "None" : garages.some((g) => g.target_area >= 28) ? "Double" : "Single";
  const footprintArea = intent.footprint_width * intent.footprint_depth;

  const facts: [string, string][] = [
    ["Building", label(intent.building_type)],
    ["Style", label(intent.style)],
    ["Floors", String(intent.floors)],
    ["Bedrooms", String(count("bedroom"))],
    ["Bathrooms", String(count("bathroom") + count("ensuite"))],
    ["Garage", garage],
    ["Footprint", `${metres(intent.footprint_width)} x ${metres(intent.footprint_depth)}`],
    ...(plan ? ([["Floor area", `${plan.summary.gross_floor_area.toFixed(0)} m²`], ["Height", metres(plan.summary.total_height)]] as [string, string][]) : []),
    ["Roof", `${label(intent.roof.type)}, ${intent.roof.pitch}°, ${label(intent.roof.material).toLowerCase()}`],
  ];

  return (
    <article aria-labelledby="review-title" className="flex min-w-0 flex-1 flex-col border border-ink/70 bg-surface">
      <header className="border-b border-ink/70 px-6 py-5">
        <h2 id="review-title" className="text-[30px] font-semibold leading-tight tracking-tight [font-stretch:112%]">
          {intent.project_name}
        </h2>
        <p className="mt-2 max-w-[70ch] text-[15px] leading-relaxed text-muted">{intent.summary}</p>
        {saveBar}
      </header>

      <dl className="grid grid-cols-2 border-b border-ink/70 sm:grid-cols-4">
        {facts.map(([term, value], i) => (
          <div key={term} className={`border-line px-4 py-3 ${i % 4 !== 3 ? "sm:border-r" : ""} ${i % 2 === 0 ? "border-r sm:border-r" : ""} ${i < 4 ? "border-b" : "max-sm:border-b"}`}>
            <dt className="text-[13px] text-muted">{term}</dt>
            <dd className="text-[17px] font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="border-b border-ink/70 px-6 py-5">
        {plan && <FloorPlans plans={plan.plans} />}
        {planning && (
          <p className="text-[15px] text-muted" aria-live="polite">Laying out the floor plans...</p>
        )}
        {planError && (
          <div role="alert" className="border-l-2 border-revision pl-3">
            <p className="text-[15px] font-medium">The floor plan could not be laid out.</p>
            <p className="mt-1 text-[15px] leading-relaxed">{planError.message}</p>
            <p className="mt-1 text-[13px] text-muted">Use Modify design to adjust the brief, for example a larger footprint or fewer rooms.</p>
          </div>
        )}
      </div>

      {plan && <ModifyPanel history={history} busy={modifying} error={modifyError} unavailableReason={modifyUnavailableReason} onModify={onChange} />}

      <div className="grid flex-1 gap-8 px-6 py-5 min-[1700px]:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-label="Rooms by floor" className="flex flex-col gap-6">
          {Array.from({ length: intent.floors }, (_, level) => {
            const rooms = intent.rooms.filter((r) => r.floor === level);
            const total = rooms.reduce((sum, r) => sum + r.target_area, 0);
            return (
              <div key={level}>
                <div className="flex items-baseline justify-between border-b border-ink/70 pb-1">
                  <h3 className="text-[17px] font-semibold">{floorName(level)}: requested rooms</h3>
                  <p className="text-[13px] tabular-nums text-muted">
                    {total.toFixed(0)} m² planned of {footprintArea.toFixed(0)} m²
                  </p>
                </div>
                <table className="w-full text-[15px]">
                  <caption className="sr-only">Rooms on the {floorName(level).toLowerCase()}</caption>
                  <thead className="sr-only">
                    <tr><th>Room</th><th>Windows</th><th>Area</th></tr>
                  </thead>
                  <tbody>
                    {rooms.map((room) => (
                      <tr key={room.id} className="border-b border-line last:border-b-0">
                        <td className="py-1.5 pr-3">
                          {room.name}
                          {room.id === intent.entrance_room && <span className="ml-2 text-[13px] text-muted">entrance</span>}
                        </td>
                        <td className="py-1.5 pr-3 text-[13px] text-muted">{GLAZING_TEXT[room.glazing]}</td>
                        <td className="whitespace-nowrap py-1.5 text-right tabular-nums">{room.target_area.toFixed(1)} m²</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </section>

        <aside className="flex flex-col gap-6">
          {intent.assumptions.length > 0 && (
            <section aria-labelledby="assumptions-title">
              <h3 id="assumptions-title" className="text-[17px] font-semibold">Assumptions Claude made</h3>
              <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[15px] leading-snug">
                {intent.assumptions.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </section>
          )}

          {result.constraints_applied.length > 0 && (
            <section aria-labelledby="applied-title">
              <h3 id="applied-title" className="text-[17px] font-semibold">Your options applied</h3>
              <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[15px] leading-snug">
                {result.constraints_applied.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </section>
          )}

          {plan && plan.notes.length > 0 && (
            <section aria-labelledby="planner-title">
              <h3 id="planner-title" className="text-[17px] font-semibold">How the plan differs from the brief</h3>
              <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5 text-[15px] leading-snug">
                {plan.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </section>
          )}

          <ValidationPanel
            reports={plan ? [plan.report, report] : [report]}
            names={Object.fromEntries([
              ...intent.rooms.map((r) => [r.id, r.name] as [string, string]),
              ...(((plan?.specification as { rooms?: { id: string; name: string }[] } | undefined)?.rooms) ?? []).map((r) => [r.id, r.name] as [string, string]),
            ])}
          />
        </aside>
      </div>

      <footer className="flex flex-col gap-3 border-t border-ink/70 px-6 py-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[13px] leading-snug text-muted">
            Interpreted by {result.model} in {result.attempts} {result.attempts === 1 ? "attempt" : "attempts"}
            {plan ? ", then laid out and validated" : ""}.
          </p>
          <div className="flex shrink-0 gap-2">
            <button type="button" onClick={onModify} className="rounded-[3px] border border-line bg-surface px-3.5 py-2 text-[15px] font-medium hover:border-ink">
              Edit brief
            </button>
            <button
              type="button"
              onClick={onApprove}
              disabled={buildUnavailableReason !== null || build.kind === "building"}
              aria-describedby="build-status"
              className="rounded-[3px] bg-ink px-3.5 py-2 text-[15px] font-medium text-surface hover:bg-ink/85 disabled:cursor-not-allowed disabled:bg-ink/35"
            >
              {build.kind === "building" ? "Building in Blender..." : build.kind === "success" ? "Build again" : "Approve and generate"}
            </button>
          </div>
        </div>
        <div id="build-status" aria-live="polite" className="text-[13px] leading-snug">
          {buildUnavailableReason && build.kind === "idle" && <p className="text-muted">{buildUnavailableReason}</p>}
          {build.kind === "building" && <p className="text-muted">Blender is building the model. This usually takes a few seconds.</p>}
          {build.kind === "success" && (
            <p>
              Built in Blender {build.result.blender_version}: {build.result.object_count} objects
              {build.result.duration_seconds > 0 ? ` in ${build.result.duration_seconds.toFixed(1)} s` : ""}.{" "}
              <a href={build.result.blend_url} download="building.blend" className="font-medium text-ink underline underline-offset-2">
                Download the .blend file
              </a>
              <span className="text-muted"> (the house with materials, site, lighting presets and cameras).</span>
            </p>
          )}
          {build.kind === "error" && <p role="alert" className="border-l-2 border-revision pl-2">{build.message}</p>}
        </div>
      </footer>
      {build.kind === "success" && <RenderPanel cameras={build.result.cameras} state={renders} onRender={onRender} />}
    </article>
  );
}
