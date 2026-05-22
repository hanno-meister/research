import type { VanguardStreamValues } from "../../types";

export const mockPipelineValues: VanguardStreamValues = {
  research_intent: `Create a technical trend-scouting report.

Research Mission: Generative 3D World Models & Spatial Intelligence

Mission Brief: Explore emerging world generation models for spatial computing. Focus on recent systems, practical capabilities, limitations, benchmarks, and scouting recommendations.`,
  research_brief:
    "Investigate recent technical progress in generative 3D world models for spatial computing, separating explicit user goals from inferred scouting dimensions. Required coverage should include named systems from the Lance context, practical capabilities, limitations, benchmarks, and deployment relevance. Sources outside the provided date window should be flagged rather than silently used.",
  research_tasks: [
    {
      id: "task-1",
      objective:
        "Scout World Labs Marble and adjacent World Labs generative world model offerings for capabilities, technical claims, access status, and spatial-computing integration relevance.",
      rationale:
        "World Labs Marble is a required coverage target and central to the spatial intelligence framing around consistent, navigable, editable 3D worlds.",
      key_questions: ["inputs", "outputs", "consistency", "integration", "limitations"],
      target_terms: ["World Labs Marble", "spatial intelligence", "generative world model"],
      boundaries: ["Focus on World Labs", "Flag older sources"],
      effort: "high",
    },
    {
      id: "task-2",
      objective:
        "Scout NVIDIA Cosmos as a world foundation model platform for 3D and spatial intelligence workflows, including model family, simulation stack, APIs, and workflow relevance.",
      rationale:
        "NVIDIA Cosmos may represent a simulation and world-foundation-model approach distinct from direct text-to-3D scene generation.",
      key_questions: ["capabilities", "3D outputs", "ecosystem", "benchmarks", "constraints"],
      target_terms: ["NVIDIA Cosmos", "Omniverse", "OpenUSD"],
      boundaries: ["Focus on Cosmos", "Use current sources"],
      effort: "high",
    },
    {
      id: "task-3",
      objective:
        "Inventory and evaluate leading text, image, and multimodal-to-3D platforms relevant to production-ready spatial computing workflows.",
      rationale:
        "Text-to-3D platforms provide the broader competitive and adoption landscape beyond named flagship systems.",
      key_questions: ["platforms", "formats", "editing", "consistency", "access"],
      target_terms: ["text-to-3D", "image-to-3D", "OpenUSD", "Unity", "Unreal Engine"],
      boundaries: ["Separate assets from worlds", "Flag older launch materials"],
      effort: "medium",
    },
  ],
  research_findings: [
    {
      summary:
        "World generation systems are moving from static asset generation toward persistent, explorable environments.",
      source_ids: ["source-1", "source-2"],
      evidence_paths: ["/evidence/source-1.md"],
      confidence: "high",
    },
    {
      summary:
        "Spatial consistency, controllability, and evaluation remain key constraints for production use.",
      source_ids: ["source-3"],
      evidence_paths: ["/evidence/source-3.md"],
      confidence: "medium",
    },
  ],
  research_sources: [
    {
      source_id: "source-1",
      title: "Example official product announcement",
      url: "https://example.com/world-generation-announcement",
      domain: "example.com",
    },
    {
      source_id: "source-2",
      title: "Example research paper",
      url: "https://arxiv.org/abs/example",
      domain: "arxiv.org",
    },
    {
      source_id: "source-3",
      title: "Example technical benchmark report",
      url: "https://example.org/benchmark-report",
      domain: "example.org",
    },
  ],
  evidence_artifacts: [
    {
      source_id: "source-1",
      path: "/evidence/source-1.md",
      character_count: 4200,
    },
    {
      source_id: "source-2",
      path: "/evidence/source-2.md",
      character_count: 3800,
    },
    {
      source_id: "source-3",
      path: "/evidence/source-3.md",
      character_count: 2900,
    },
  ],
  research_reviews: [
    {
      sufficient: true,
      summary:
        "Evidence is sufficient for a first-pass scouting report, with clear caveats around benchmark maturity.",
      follow_up_tasks: [
        "Validate export and editing workflows in a live product test.",
        "Re-run the benchmark scan if new systems ship this quarter.",
      ],
      missing_evidence: [],
    },
  ],
  evidence_read_records: [
    {
      source_id: "source-1",
      path: "/evidence/source-1.md",
      character_count: 4200,
    },
    {
      source_id: "source-3",
      path: "/evidence/source-3.md",
      character_count: 2900,
    },
  ],
  research_feasibility_notes: [
    "Mock note: selected domains provide enough coverage for a first scouting pass.",
  ],
  source_diversity_notes: [
    "Mock note: evidence mixes official announcements, academic sources, and benchmark-style analysis.",
  ],
  final_report: `# Generative 3D World Models & Spatial Intelligence

## Executive summary

Generative world models are shifting from isolated 3D asset creation toward systems that can produce coherent, explorable environments. For spatial computing teams, the near-term opportunity is not full autonomous world simulation, but faster ideation, scene prototyping, and synthetic environment generation for design and testing workflows.

## Key findings

- Recent systems increasingly emphasize environment consistency, camera movement, and interactive exploration rather than single-object generation.
- Production readiness is still constrained by controllability, temporal consistency, evaluation quality, and integration with existing 3D pipelines.
- The most useful scouting targets are tools that expose controllable scene generation, editing, export paths, or APIs that fit spatial workflows.

## Evidence snapshot

| Signal | Read |
| --- | --- |
| Official product updates | Strong |
| Academic breadth | Moderate |
| Benchmark maturity | Weak |

> Recommendation: keep monitoring, but validate with hands-on workflow tests before making platform commitments.

## Scouting recommendation

Track this area closely, but evaluate candidates through workflow pilots rather than demos alone. Prioritize systems that can be tested against concrete spatial computing tasks: rapid environment blocking, synthetic test scenes, concept visualization, and world-state iteration.`,
};
