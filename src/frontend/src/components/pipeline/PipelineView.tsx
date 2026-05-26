import type { VanguardStreamValues } from "../../types";
import { StageCard, type StageStatus } from "./StageCard";
import { BriefStage } from "./stages/BriefStage";
import { PlanStage } from "./stages/PlanStage";
import { ResearchStage } from "./stages/ResearchStage";
import { ReportStage } from "./stages/ReportStage";
import { ReviewStage } from "./stages/ReviewStage";

interface PipelineViewProps {
  values: VanguardStreamValues | undefined;
  isLoading: boolean;
}

function hasItems(value: unknown): boolean {
  return Array.isArray(value) && value.length > 0;
}

function getStageStatuses(
  values: VanguardStreamValues | undefined,
  isLoading: boolean,
): Record<string, StageStatus> {
  const reviews = Array.isArray(values?.research_reviews) ? values.research_reviews : [];
  const latestReview = reviews.at(-1);
  const latestReviewNeedsRepair =
    latestReview !== undefined &&
    latestReview.sufficient === false &&
    Array.isArray(latestReview.follow_up_tasks) &&
    latestReview.follow_up_tasks.length > 0 &&
    !values?.final_report;
  const completed = [
    Boolean(values?.research_brief || values?.research_question),
    hasItems(values?.research_tasks),
    hasItems(values?.research_findings) || hasItems(values?.research_sources),
    hasItems(values?.research_reviews) && !latestReviewNeedsRepair,
    Boolean(values?.final_report),
  ];

  const runningIndex = isLoading ? completed.findIndex((isDone) => !isDone) : -1;

  return {
    brief: completed[0] ? "complete" : runningIndex === 0 ? "running" : "pending",
    plan: completed[1] ? "complete" : runningIndex === 1 ? "running" : "pending",
    research: completed[2] ? "complete" : runningIndex === 2 ? "running" : "pending",
    review: completed[3] ? "complete" : runningIndex === 3 ? "running" : "pending",
    report: completed[4] ? "complete" : runningIndex === 4 ? "running" : "pending",
  };
}

export function PipelineView({ values, isLoading }: PipelineViewProps) {
  const statuses = getStageStatuses(values, isLoading);

  return (
    <div className="relative isolate grid min-h-0 gap-4 xl:grid-cols-4">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-64 bg-[radial-gradient(circle_at_top_left,rgba(6,182,212,0.14),transparent_32%),radial-gradient(circle_at_top_right,rgba(34,197,94,0.12),transparent_28%),radial-gradient(circle_at_bottom,rgba(245,158,11,0.08),transparent_35%)] blur-2xl" />

      <StageCard
        title="Brief"
        description="Turns the mission input into a focused research brief."
        status={statuses.brief}
        className="lg:col-span-2 xl:col-span-2"
      >
        <BriefStage values={values} />
      </StageCard>

      <StageCard
        title="Plan"
        description="Breaks the brief into concrete research tasks."
        status={statuses.plan}
        className="lg:col-span-2 xl:col-span-2"
      >
        <PlanStage values={values} />
      </StageCard>

      <StageCard
        title="Research"
        description="Runs searches, gathers findings, and records evidence."
        status={statuses.research}
        className="lg:col-span-2 xl:col-span-2"
      >
        <ResearchStage values={values} />
      </StageCard>

      <StageCard
        title="Review"
        description="Checks evidence quality, feasibility, and remaining gaps."
        status={statuses.review}
        className="lg:col-span-2 xl:col-span-2"
      >
        <ReviewStage values={values} />
      </StageCard>

      <StageCard
        title="Final Report"
        description="Synthesizes the reviewed evidence into the final trend-scouting report."
        status={statuses.report}
        className="xl:col-span-4"
      >
        <ReportStage values={values} />
      </StageCard>
    </div>
  );
}
