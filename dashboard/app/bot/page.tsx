export const dynamic = "force-dynamic";

import { Navbar } from "@/components/navbar";
import { Footer } from "@/components/footer";
import { BotMonitor } from "@/components/bot-monitor";

export default function BotPage() {
  return (
    <div className="min-h-screen flex flex-col overflow-x-hidden">
      <Navbar />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 md:px-6 py-6 md:py-10">
        <BotMonitor />
      </main>
      <Footer />
    </div>
  );
}
