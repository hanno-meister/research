import { PipelineView } from "../../components/pipeline/PipelineView";
import { mockPipelineValues } from "./mockPipelineValues";

export function MockPipelineView() {
  return <PipelineView values={mockPipelineValues} isLoading={false} />;
}
