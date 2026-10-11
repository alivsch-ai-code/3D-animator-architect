import type { ProjectStatus } from "@/lib/types";
import { STATUS_LABELS } from "@/lib/types";

const STYLES: Record<ProjectStatus, string> = {
  created: "bg-neutral-100 text-neutral-600 ring-neutral-300",
  uploaded: "bg-sky-50 text-sky-700 ring-sky-200",
  parsed: "bg-amber-50 text-amber-700 ring-amber-200",
  model_generated: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  rendered: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  failed: "bg-red-50 text-red-700 ring-red-200",
};

export default function StatusBadge({ status }: { status: ProjectStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATUS_LABELS[status]}
    </span>
  );
}
