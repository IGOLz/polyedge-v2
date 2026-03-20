"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const result = await signIn("credentials", {
      password,
      redirect: false,
    });

    if (result?.error) {
      setError("Invalid password");
      setLoading(false);
    } else {
      router.push("/control");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/50 backdrop-blur-sm p-8">
          <div className="mb-6 text-center">
            <div className="mx-auto mb-3 flex h-3 w-3 items-center justify-center">
              <div className="absolute h-3 w-3 rounded-full bg-primary animate-ping opacity-20" />
              <div className="h-3 w-3 rounded-full bg-primary shadow-sm shadow-primary/50" />
            </div>
            <h1 className="text-2xl font-bold text-primary">PolyEdge</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Enter password to access control panel
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-zinc-300"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter dashboard password"
                autoFocus
                className="w-full rounded-lg border border-zinc-800/60 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 outline-none transition-colors focus:border-primary/50 focus:ring-1 focus:ring-primary/30"
              />
            </div>

            {error && (
              <p className="text-sm font-medium text-red-400">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-zinc-950 transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
