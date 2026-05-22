import { useState } from "react";
import { X, Plus, Trash2 } from "lucide-react";

interface DomainChipInputProps {
  domains: string[];
  onChange: (domains: string[]) => void;
}

const inputClass =
  "flex-1 bg-bg-primary border border-border rounded-lg px-4 py-2.5 text-text-primary placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-accent-cyan/50 transition-all";

export function DomainChipInput({ domains, onChange }: DomainChipInputProps) {
  const [inputValue, setInputValue] = useState("");

  const addDomain = () => {
    const trimmed = inputValue.trim().toLowerCase();
    if (trimmed && !domains.includes(trimmed)) {
      onChange([...domains, trimmed]);
    }
    setInputValue("");
  };

  const removeDomain = (domain: string) => {
    onChange(domains.filter((d) => d !== domain));
  };

  const clearAll = () => {
    onChange([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addDomain();
    }
  };

  return (
    <div>
      <label className="block text-sm font-medium text-text-secondary mb-2">
        Query Domains (optional)
      </label>

      <div className="flex gap-2">
        <input
          type="text"
          className={inputClass}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter domains (e.g., openai.com)"
        />
        <button
          type="button"
          onClick={addDomain}
          className="bg-accent-cyan hover:bg-accent-cyan/80 text-white px-4 py-2.5 rounded-lg transition-colors flex items-center gap-2 font-medium cursor-pointer shrink-0"
        >
          <Plus className="w-4 h-4" />
          Add Domain
        </button>
        <button
          type="button"
          onClick={clearAll}
          className="bg-accent-red/10 hover:bg-accent-red/20 text-accent-red border border-accent-red/20 px-4 py-2.5 rounded-lg transition-colors flex items-center gap-2 font-medium cursor-pointer shrink-0"
        >
          <Trash2 className="w-4 h-4" />
          Clear Domains
        </button>
      </div>

      {domains.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {domains.map((domain) => (
            <span
              key={domain}
              className="flex items-center gap-1.5 bg-accent-cyan/10 border border-accent-cyan/20 text-accent-cyan px-3 py-1 rounded-full text-sm font-medium"
            >
              {domain}
              <button
                type="button"
                onClick={() => removeDomain(domain)}
                className="hover:bg-accent-red hover:text-white rounded-full p-0.5 transition-colors cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
