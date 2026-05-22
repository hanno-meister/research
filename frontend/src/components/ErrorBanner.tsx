import { AlertTriangle, X } from "lucide-react";

interface ErrorBannerProps {
  message: string;
  onDismiss: () => void;
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 w-full max-w-lg px-4">
      <div className="bg-accent-red/10 border border-accent-red/20 backdrop-blur-md rounded-xl p-4 flex items-start gap-4 shadow-2xl">
        <div className="p-2 bg-accent-red/20 rounded-lg shrink-0">
          <AlertTriangle className="w-5 h-5 text-accent-red" />
        </div>
        <div className="flex-1 pt-1">
          <h4 className="text-sm font-bold text-accent-red uppercase tracking-wider mb-1">
            Error
          </h4>
          <p className="text-sm text-accent-red/80 leading-relaxed">
            {message}
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="p-1 hover:bg-accent-red/20 rounded-md transition-colors text-accent-red"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
