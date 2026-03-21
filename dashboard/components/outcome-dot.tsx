import { cn } from "@/lib/utils";
import { getOutcomeColors } from "@/lib/formatters";

interface OutcomeDotProps {
  outcome: string | null;
  size?: "sm" | "md";
}

const sizes = {
  sm: "h-2 w-2",
  md: "h-2.5 w-2.5",
};

export function OutcomeDot({ outcome, size = "sm" }: OutcomeDotProps) {
  const { bg } = getOutcomeColors(outcome);
  return <span className={cn("rounded-full", sizes[size], bg)} />;
}
