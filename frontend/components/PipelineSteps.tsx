import type { ProjectStatus } from "@/lib/types";

const STEPS: { key: ProjectStatus; label: string; icon: string }[] = [
  { key: "uploaded", label: "Grundriss", icon: "📐" },
  { key: "parsed", label: "Analyse", icon: "🔍" },
  { key: "model_generated", label: "3D-Modell", icon: "🧱" },
  { key: "rendered", label: "Rendering", icon: "✨" },
];

const ORDER: ProjectStatus[] = [
  "created",
  "uploaded",
  "parsed",
  "model_generated",
  "rendered",
];

export default function PipelineSteps({ status }: { status: ProjectStatus }) {
  const currentIndex = ORDER.indexOf(status);

  return (
    <ol className="flex items-center gap-2 sm:gap-4">
      {STEPS.map((step, i) => {
        const stepIndex = ORDER.indexOf(step.key);
        const done = currentIndex >= stepIndex;
        const active = currentIndex === stepIndex;
        return (
          <li key={step.key} className="flex items-center gap-2 sm:gap-4">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`flex h-9 w-9 items-center justify-center rounded-full text-sm ring-2 transition-colors ${
                  done
                    ? "bg-accent text-white ring-accent"
                    : "bg-white text-neutral-400 ring-neutral-200"
                } ${active ? "scale-110" : ""}`}
              >
                {step.icon}
              </div>
              <span
                className={`text-[11px] whitespace-nowrap ${
                  done ? "text-neutral-800 font-medium" : "text-neutral-400"
                }`}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`h-0.5 w-6 sm:w-10 rounded ${
                  currentIndex > stepIndex ? "bg-accent" : "bg-neutral-200"
                }`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
