import type { VanguardStreamValues } from "../../../types";

interface BriefStageProps {
  values: VanguardStreamValues | undefined;
}

export function BriefStage({ values }: BriefStageProps) {
  const brief = values?.research_brief;

  if (!brief) {
    return (
      <p className="rounded-xl border border-dashed border-border bg-bg-primary/50 p-4 text-text-secondary">
        Waiting for the research brief…
      </p>
    );
  }

  return (
    <p className="whitespace-pre-wrap rounded-lg border border-border bg-bg-primary p-3 text-sm leading-6 text-text-primary">
      {String(brief)}
    </p>
  );
}
