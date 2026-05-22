import { useResearchStore } from "./store/researchStore";
import { useResearchStream } from "./hooks/useResearchStream";
import { ResearchForm } from "./components/ResearchForm";
import { Dashboard } from "./components/Dashboard";
import { ErrorBanner } from "./components/ErrorBanner";

function ResearchSession() {
  const { runStatus, showForm } = useResearchStore();
  const stream = useResearchStream();

  if (showForm && runStatus === "idle") {
    return (
      <div className="flex items-center justify-center min-h-screen p-4">
        <ResearchForm
          onSubmit={stream.startResearch}
          isLoading={stream.isLoading}
        />
      </div>
    );
  }
  return <Dashboard stream={stream} />;
}

export default function App() {
  const { error, setError, sessionKey } = useResearchStore();

  return (
    <div className="min-h-screen bg-bg-primary text-text-primary">
      {error && (
        <ErrorBanner message={error} onDismiss={() => setError(null)} />
      )}
      <ResearchSession key={sessionKey} />
    </div>
  );
}
