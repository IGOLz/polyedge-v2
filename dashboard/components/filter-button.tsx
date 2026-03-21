import { cn } from "@/lib/utils";

interface FilterButtonProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

export function FilterButton({ label, active, onClick }: FilterButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-md px-3 py-1.5 text-sm font-semibold uppercase tracking-wide transition-all duration-200",
        active
          ? "bg-primary/15 text-primary border border-primary/25"
          : "text-zinc-300 border border-transparent hover:bg-zinc-800/50 hover:text-zinc-300"
      )}
    >
      {label}
    </button>
  );
}
