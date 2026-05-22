import { useState } from "react";
import type { ResearchInput } from "../types";
import { Loader2, Zap } from "lucide-react";
import lancePresets from "../presets/lancePresets.json";
import standardDomains from "../presets/standardDomains.json";
import { DomainChipInput } from "./DomainChipInput";

interface ResearchFormProps {
  onSubmit: (input: ResearchInput) => void;
  isLoading: boolean;
}

const INITIAL_FORM: ResearchInput = {
  lance_name: "",
  lance_description: "",
  selected_lance: null,
  start_date: "",
  end_date: "",
  query_domains: standardDomains,
};

const inputClass =
  "w-full bg-bg-primary border border-border rounded-lg px-4 py-2.5 text-text-primary placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 transition-all";

export function ResearchForm({ onSubmit, isLoading }: ResearchFormProps) {
  const [form, setForm] = useState<ResearchInput>(INITIAL_FORM);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (form.start_date && form.end_date && form.start_date > form.end_date) {
      setValidationError("Start date must be before end date.");
      return;
    }

    setValidationError(null);
    onSubmit(form);
  };

  return (
    <div className="w-full max-w-2xl bg-bg-secondary border border-border rounded-xl p-8 shadow-2xl">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-accent-cyan/10 rounded-lg">
          <Zap className="w-6 h-6 text-accent-cyan" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight">
          New Research Mission
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-2">
            Mission Name *
          </label>
          <select
            required
            className={inputClass}
            value={form.lance_name}
            onChange={(e) => {
              const selected = lancePresets.find((p) => p.name === e.target.value);
              const description = selected?.description ?? form.lance_description;
              setForm({
                ...form,
                lance_name: e.target.value,
                lance_description: description,
                selected_lance: e.target.value
                  ? { name: e.target.value, description }
                  : null,
              });
            }}
          >
            <option value="">— Select a mission —</option>
            {lancePresets.map((preset) => (
              <option key={preset.id} value={preset.name}>
                {preset.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-text-secondary mb-2">
            Description
          </label>
          <textarea
            rows={3}
            className={`${inputClass} resize-none`}
            value={form.lance_description}
            onChange={(e) =>
              setForm({
                ...form,
                lance_description: e.target.value,
                selected_lance: form.lance_name
                  ? { name: form.lance_name, description: e.target.value }
                  : null,
              })
            }
            placeholder="What exactly are we looking for?"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              Start Date
            </label>
            <input
              type="date"
              className={inputClass}
              value={form.start_date}
              onChange={(e) =>
                setForm({ ...form, start_date: e.target.value })
              }
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-2">
              End Date
            </label>
            <input
              type="date"
              className={inputClass}
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </div>
        </div>

        <DomainChipInput
          domains={form.query_domains}
          onChange={(domains) => setForm({ ...form, query_domains: domains })}
        />

        {validationError && (
          <p className="text-sm text-accent-red">{validationError}</p>
        )}

        <button
          type="submit"
          disabled={isLoading || !form.lance_name.trim()}
          className="w-full bg-accent-cyan hover:bg-accent-cyan/80 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 cursor-pointer"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            "Launch Mission"
          )}
        </button>
      </form>
    </div>
  );
}
