import { type RefObject, useId, useState } from "react";

import type { DesignConstraints } from "../types/design";
import { EXAMPLE_PROMPTS, MAX_PROMPT_LENGTH, MIN_PROMPT_LENGTH } from "../utils/examplePrompts";
import { AdvancedOptions } from "./AdvancedOptions";

const buttonBase =
  "rounded-[3px] px-3.5 py-2 text-[15px] font-medium transition-colors disabled:cursor-not-allowed";

interface Props {
  prompt: string;
  onPromptChange: (value: string) => void;
  constraints: DesignConstraints;
  onConstraintsChange: (value: DesignConstraints) => void;
  onGenerate: () => void;
  busy: boolean;
  /** Why generation is unavailable right now (missing API key, backend down), if it is. */
  unavailableReason: string | null;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

export function PromptPanel({ prompt, onPromptChange, constraints, onConstraintsChange, onGenerate, busy, unavailableReason, textareaRef }: Props) {
  const [exampleIndex, setExampleIndex] = useState(0);
  const inputId = useId();
  const hintId = useId();

  const tooShort = prompt.trim().length < MIN_PROMPT_LENGTH;
  const canGenerate = !busy && !tooShort && unavailableReason === null;
  const hint = unavailableReason ?? (tooShort ? `Write at least ${MIN_PROMPT_LENGTH} characters to describe the building.` : null);

  const showNextExample = () => {
    onPromptChange(EXAMPLE_PROMPTS[exampleIndex % EXAMPLE_PROMPTS.length] ?? "");
    setExampleIndex((i) => i + 1);
  };

  return (
    <section aria-labelledby={`${inputId}-heading`} className="flex flex-col gap-4">
      <h2 id={`${inputId}-heading`} className="text-[22px] font-semibold tracking-tight [font-stretch:110%]">
        Brief
      </h2>

      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (canGenerate) onGenerate();
        }}
      >
        <div className="flex flex-col gap-2">
          <label htmlFor={inputId} className="text-[15px] font-medium">
            Describe the building you want to create
          </label>
          <textarea
            id={inputId}
            ref={textareaRef}
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            maxLength={MAX_PROMPT_LENGTH}
            rows={8}
            readOnly={busy}
            aria-describedby={hint ? hintId : undefined}
            placeholder="A contemporary two-storey UK family house with three bedrooms, two bathrooms, an open-plan kitchen and living area, an office, a garage and a rear patio."
            className="min-h-44 resize-y rounded-[3px] border border-line bg-surface p-3 text-[15px] leading-relaxed placeholder:text-muted/80 focus:border-ink focus:outline-none read-only:text-muted"
          />
          <p className="text-right text-[13px] tabular-nums text-muted" aria-live="polite">
            {prompt.length.toLocaleString("en-GB")} of {MAX_PROMPT_LENGTH.toLocaleString("en-GB")} characters
          </p>
        </div>

        <AdvancedOptions value={constraints} onChange={onConstraintsChange} disabled={busy} />

        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={!canGenerate} className={`${buttonBase} bg-ink text-surface hover:bg-ink/85 disabled:bg-ink/35`}>
            {busy ? "Interpreting..." : "Generate design"}
          </button>
          <button type="button" onClick={showNextExample} disabled={busy} className={`${buttonBase} border border-line bg-surface hover:border-ink disabled:opacity-50`}>
            Example prompt
          </button>
          <button
            type="button"
            onClick={() => onPromptChange("")}
            disabled={busy || prompt.length === 0}
            className={`${buttonBase} text-muted hover:text-ink disabled:text-muted/50`}
          >
            Clear
          </button>
        </div>
      </form>

      {hint && (
        <p id={hintId} className="border-l-2 border-revision pl-3 text-[13px] leading-relaxed text-muted">
          {hint}
        </p>
      )}
    </section>
  );
}
