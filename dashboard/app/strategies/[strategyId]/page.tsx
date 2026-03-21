export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";

import { StrategyDetailPage } from "@/components/strategy-detail-page";
import { getStrategyDetail } from "@/lib/strategy-artifacts";

export default async function StrategyDynamicPage({
  params,
}: {
  params: { strategyId: string };
}) {
  const detail = await getStrategyDetail(params.strategyId);

  if (!detail) {
    notFound();
  }

  return <StrategyDetailPage detail={detail} />;
}
