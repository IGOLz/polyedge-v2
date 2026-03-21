export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";

import { StrategyDetailPage } from "@/components/strategy-detail-page";
import { getStrategyDetail } from "@/lib/strategy-artifacts";

export default async function LegacyStrategy3Page() {
  const detail = await getStrategyDetail("S3");

  if (!detail) {
    notFound();
  }

  return <StrategyDetailPage detail={detail} />;
}
