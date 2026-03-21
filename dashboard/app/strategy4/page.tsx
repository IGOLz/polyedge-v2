export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";

import { StrategyDetailPage } from "@/components/strategy-detail-page";
import { getStrategyDetail } from "@/lib/strategy-artifacts";

export default async function LegacyStrategy4Page() {
  const detail = await getStrategyDetail("S4");

  if (!detail) {
    notFound();
  }

  return <StrategyDetailPage detail={detail} />;
}
