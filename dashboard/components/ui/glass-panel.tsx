import { cn } from "@/lib/utils";

export type GlowVariant =
  | "glow-tr"
  | "glow-tl"
  | "glow-br"
  | "glow-center"
  | "glow-split"
  | "glow-wide"
  | "subtle";

function GlowOverlay({ variant }: { variant: GlowVariant }) {
  switch (variant) {
    case "glow-tr":
      return (
        <>
          <div className="absolute -top-10 -right-10 h-24 w-24 rounded-full bg-primary/[0.05] blur-2xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent pointer-events-none" />
        </>
      );
    case "glow-tl":
      return (
        <>
          <div className="absolute -top-10 -left-10 h-24 w-24 rounded-full bg-primary/[0.04] blur-2xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.03] to-transparent pointer-events-none" />
        </>
      );
    case "glow-br":
      return (
        <>
          <div className="absolute -bottom-10 -right-10 h-28 w-28 rounded-full bg-primary/[0.05] blur-3xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-t from-primary/[0.02] to-transparent pointer-events-none" />
        </>
      );
    case "glow-center":
      return (
        <>
          <div className="absolute -top-16 left-1/2 -translate-x-1/2 h-32 w-48 rounded-full bg-primary/[0.04] blur-3xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] via-transparent to-transparent pointer-events-none" />
        </>
      );
    case "glow-split":
      return (
        <>
          <div className="absolute -top-8 -left-8 h-20 w-20 rounded-full bg-primary/[0.04] blur-2xl pointer-events-none" />
          <div className="absolute -bottom-8 -right-8 h-20 w-20 rounded-full bg-primary/[0.03] blur-2xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.02] via-transparent to-primary/[0.01] pointer-events-none" />
        </>
      );
    case "glow-wide":
      return (
        <>
          <div className="absolute -top-6 inset-x-0 mx-auto h-12 w-2/3 rounded-full bg-primary/[0.04] blur-3xl pointer-events-none" />
          <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.03] to-transparent pointer-events-none" />
        </>
      );
    case "subtle":
      return (
        <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.015] to-transparent pointer-events-none" />
      );
  }
}

interface GlassPanelProps {
  variant?: GlowVariant;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

export function GlassPanel({
  variant = "glow-tr",
  className,
  style,
  children,
}: GlassPanelProps) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-xl border border-primary/20 bg-zinc-950",
        className
      )}
      style={style}
    >
      <div className="absolute inset-x-0 top-0 z-10 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
      <GlowOverlay variant={variant} />
      {children}
    </div>
  );
}
