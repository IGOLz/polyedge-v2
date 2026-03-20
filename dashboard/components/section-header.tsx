import { SectionInfoButton } from "@/components/section-info-modal";

interface SectionHeaderProps {
  title: string;
  description?: string;
  exportData?: unknown;
}

export function SectionHeader({ title, description, exportData }: SectionHeaderProps) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-zinc-100">
          {title}
        </h2>
        <SectionInfoButton sectionTitle={title} exportData={exportData} />
        <div className="h-px flex-1 bg-gradient-to-r from-zinc-700/60 to-transparent" />
      </div>
      {description && (
        <p className="mt-1.5 text-sm text-zinc-400">{description}</p>
      )}
    </div>
  );
}
