import { cn } from "@/lib/utils";

const DownloadIcon = ({ size = 14 }: { size?: number }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

const baseStyles =
  "flex items-center gap-1.5 rounded-lg border border-zinc-800/60 bg-zinc-900/50 px-3 py-1.5 text-sm font-medium text-zinc-400 transition-all duration-200 hover:border-primary/30 hover:text-primary hover:bg-primary/5";

interface DownloadButtonProps {
  label: string;
  onClick?: () => void;
  href?: string;
  className?: string;
  iconSize?: number;
}

export function DownloadButton({
  label,
  onClick,
  href,
  className,
  iconSize = 14,
}: DownloadButtonProps) {
  if (href) {
    return (
      <a href={href} download className={cn(baseStyles, className)}>
        <DownloadIcon size={iconSize} />
        {label}
      </a>
    );
  }

  return (
    <button onClick={onClick} className={cn(baseStyles, className)}>
      <DownloadIcon size={iconSize} />
      {label}
    </button>
  );
}
