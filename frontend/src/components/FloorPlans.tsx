import { useState } from "react";

import type { FloorPlanPreview } from "../types/design";

/** Floor-plan drawings from the backend, one tab per floor.

The SVG is shown through an <img> data URL: the browser renders it as an image, so nothing
inside it can run script, even though room names come from the brief. */
export function FloorPlans({ plans }: { plans: FloorPlanPreview[] }) {
  const [active, setActive] = useState(0);
  const current = plans[Math.min(active, plans.length - 1)];
  if (!current) return null;

  return (
    <section aria-labelledby="plans-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="plans-title" className="text-[17px] font-semibold">Floor plans</h3>
        {plans.length > 1 && (
          <div role="tablist" aria-label="Floors" className="flex gap-1">
            {plans.map((plan, index) => (
              <button
                key={plan.level}
                type="button"
                role="tab"
                id={`floor-tab-${plan.level}`}
                aria-selected={index === active}
                aria-controls="floor-panel"
                onClick={() => setActive(index)}
                className={`rounded-[3px] px-3 py-1 text-[13px] font-medium ${
                  index === active ? "bg-ink text-surface" : "border border-line text-muted hover:border-ink hover:text-ink"
                }`}
              >
                {plan.name}
              </button>
            ))}
          </div>
        )}
      </div>
      <div
        id="floor-panel"
        role={plans.length > 1 ? "tabpanel" : undefined}
        aria-labelledby={plans.length > 1 ? `floor-tab-${current.level}` : undefined}
        aria-label={plans.length > 1 ? undefined : `${current.name} plan`}
        tabIndex={0} // the plan can scroll sideways on small screens, so keyboard users must be able to reach it
        className="overflow-x-auto border border-line bg-white focus-visible:outline-2"
      >
        <img
          src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(current.svg)}`}
          alt={`${current.name} plan`}
          className="mx-auto block h-auto w-full min-w-[600px] max-w-full sm:min-w-0"
        />
      </div>
      <p className="text-[13px] text-muted">
        Front of the building at the bottom. On a small screen, scroll the plan sideways. Red marks external doors, blue marks windows, dashed boxes are stairwells
        and balconies.
      </p>
    </section>
  );
}
