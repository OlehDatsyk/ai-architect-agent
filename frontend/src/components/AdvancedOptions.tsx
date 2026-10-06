import type { DesignConstraints } from "../types/design";
import { label } from "../utils/labels";

const BUILDING_TYPES = ["detached_house", "semi_detached_house", "bungalow", "apartment_building", "office", "shop", "custom"];
const STYLES = ["modern", "contemporary", "traditional_british", "victorian_inspired", "scandinavian", "mediterranean", "industrial", "minimalist", "custom"];

type NumericKey = "floors" | "width" | "depth" | "height" | "bedrooms" | "bathrooms";

const NUMBER_FIELDS: { key: NumericKey; text: string; min: number; max: number; step: number }[] = [
  { key: "floors", text: "Floors", min: 1, max: 10, step: 1 },
  { key: "bedrooms", text: "Bedrooms", min: 0, max: 12, step: 1 },
  { key: "bathrooms", text: "Bathrooms", min: 0, max: 10, step: 1 },
  { key: "width", text: "Width (m)", min: 4, max: 80, step: 0.1 },
  { key: "depth", text: "Depth (m)", min: 4, max: 80, step: 0.1 },
  { key: "height", text: "Height (m)", min: 3, max: 40, step: 0.1 },
];

const inputClass =
  "w-full rounded-[3px] border border-line bg-surface px-2 py-1.5 text-[15px] focus:border-ink focus:outline-none";

interface Props {
  value: DesignConstraints;
  onChange: (value: DesignConstraints) => void;
  disabled?: boolean;
}

export function AdvancedOptions({ value, onChange, disabled = false }: Props) {
  const set = <K extends keyof DesignConstraints>(key: K, next: DesignConstraints[K] | undefined) => {
    const updated = { ...value };
    if (next === undefined || next === "") delete updated[key];
    else updated[key] = next;
    onChange(updated);
  };
  const selected = Object.entries(value).filter(([k, v]) => v !== null && v !== undefined
    && !(k === "roof" && v === "automatic") && !(k === "detail_level" && v === "standard")).length;

  return (
    <details className="group rounded-[3px] border border-line bg-surface/60">
      <summary className="cursor-pointer select-none px-3 py-2 text-[15px] font-medium">
        Advanced options
        {selected > 0 && <span className="ml-2 text-[13px] font-normal text-muted">{selected} set</span>}
      </summary>
      <fieldset disabled={disabled} className="grid grid-cols-2 gap-3 border-t border-line p-3">
        <p className="col-span-2 text-[13px] leading-snug text-muted">
          Anything you set here overrides what the brief implies. Leave a field empty to let Claude decide.
        </p>

        <SelectField id="opt-type" text="Building type" value={value.building_type} options={BUILDING_TYPES} onChange={(v) => set("building_type", v)} />
        <SelectField id="opt-style" text="Style" value={value.style} options={STYLES} onChange={(v) => set("style", v)} />

        {NUMBER_FIELDS.map((f) => (
          <label key={f.key} className="flex flex-col gap-1 text-[13px] text-muted">
            {f.text}
            <input
              type="number"
              inputMode="decimal"
              min={f.min}
              max={f.max}
              step={f.step}
              value={value[f.key] ?? ""}
              onChange={(e) => set(f.key, e.target.value === "" ? undefined : Number(e.target.value))}
              className={`${inputClass} text-ink`}
            />
          </label>
        ))}

        <SelectField id="opt-garage" text="Garage" value={value.garage} options={["none", "single", "double"]} onChange={(v) => set("garage", v as DesignConstraints["garage"])} />
        <SelectField
          id="opt-roof"
          text="Roof"
          value={value.roof === "automatic" ? undefined : value.roof}
          options={["flat", "gable", "hip", "shed"]}
          onChange={(v) => set("roof", (v ?? "automatic") as DesignConstraints["roof"])}
        />
        <SelectField
          id="opt-detail"
          text="Detail level"
          value={value.detail_level}
          options={["concept", "standard", "detailed"]}
          emptyText="Standard"
          onChange={(v) => set("detail_level", v as DesignConstraints["detail_level"])}
        />
      </fieldset>
    </details>
  );
}

function SelectField({ id, text, value, options, onChange, emptyText = "Automatic" }: {
  id: string;
  text: string;
  value: string | undefined;
  options: string[];
  onChange: (value: string | undefined) => void;
  emptyText?: string;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-[13px] text-muted">
      {text}
      <select id={id} value={value ?? ""} onChange={(e) => onChange(e.target.value || undefined)} className={`${inputClass} text-ink`}>
        <option value="">{emptyText}</option>
        {options.map((o) => (
          <option key={o} value={o}>{label(o)}</option>
        ))}
      </select>
    </label>
  );
}
