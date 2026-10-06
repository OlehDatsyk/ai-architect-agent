import { useId, useState } from "react";

import { DEFAULT_RENDER, type RenderState } from "../hooks/useRenders";
import type { CameraInfo, RenderRequest } from "../types/design";

/** "Camera_Interior_MasterBedroom" -> "Interior master bedroom" */
export function cameraLabel(name: string): string {
  const words = name.replace(/^Camera_/, "").replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const selectClass = "rounded-[3px] border border-line bg-surface px-2 py-1.5 text-[15px] focus:border-ink focus:outline-none";

interface Props {
  cameras: CameraInfo[];
  state: RenderState;
  onRender: (request: RenderRequest) => void;
}

export function RenderPanel({ cameras, state, onRender }: Props) {
  const [request, setRequest] = useState<RenderRequest>(DEFAULT_RENDER);
  const id = useId();
  const set = <K extends keyof RenderRequest>(key: K, value: RenderRequest[K]) => setRequest((r) => ({ ...r, [key]: value }));

  const field = (key: keyof RenderRequest, label: string, options: [string, string][]) => (
    <label htmlFor={`${id}-${key}`} className="flex flex-col gap-1 text-[13px] text-muted">
      {label}
      <select id={`${id}-${key}`} value={request[key]} disabled={state.busy}
        onChange={(e) => set(key, e.target.value as never)} className={`${selectClass} text-ink`}>
        {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </label>
  );

  return (
    <section aria-labelledby={`${id}-title`} className="flex flex-col gap-4 border-t border-ink/70 px-6 py-5">
      <h3 id={`${id}-title`} className="text-[17px] font-semibold">Renders</h3>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); onRender(request); }}>
        {field("camera", "Camera", cameras.map((c) => [c.name, cameraLabel(c.name)]))}
        {field("preset", "Lighting", [["day", "Day"], ["evening", "Evening"]])}
        {field("quality", "Quality", [["preview", "Preview (fast, half size)"], ["standard", "Standard"], ["high", "High"]])}
        {field("resolution", "Resolution", [["1280x720", "1280 x 720"], ["1920x1080", "1920 x 1080"], ["2560x1440", "2560 x 1440"]])}
        {field("engine", "Engine", [["auto", "Automatic"], ["eevee", "EEVEE"], ["cycles", "Cycles"]])}
        <button type="submit" disabled={state.busy}
          className="rounded-[3px] bg-ink px-3.5 py-2 text-[15px] font-medium text-surface hover:bg-ink/85 disabled:cursor-not-allowed disabled:bg-ink/35">
          {state.busy ? "Rendering..." : "Render"}
        </button>
      </form>

      <div aria-live="polite" className="text-[13px]">
        {state.busy && <p className="text-muted">Blender is rendering. Preview takes under a minute on most machines; High quality can take several minutes.</p>}
        {state.error && <p role="alert" className="border-l-2 border-revision pl-2">{state.error}</p>}
      </div>

      {state.renders.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2">
          {state.renders.map((r) => (
            <li key={r.render_id} className="flex flex-col gap-1.5">
              <a href={r.image_url} target="_blank" rel="noreferrer" className="block border border-line bg-white">
                <img src={r.image_url} alt={`${cameraLabel(r.camera)} render, ${r.preset} lighting`} className="block h-auto w-full" />
              </a>
              <p className="text-[13px] leading-snug text-muted">
                {cameraLabel(r.camera)}, {r.preset}, {r.quality}, {r.engine === "eevee" ? "EEVEE" : "Cycles"}, {r.width} x {r.height}{r.duration_seconds > 0 ? `, ${r.duration_seconds.toFixed(0)} s` : ""}
              </p>
              {r.note && <p className="text-[13px] leading-snug">{r.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
