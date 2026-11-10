"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      const next = new URLSearchParams(window.location.search).get("next");
      // Same-site paths only, so a crafted link can't redirect off EventSphere.
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm px-6 py-20">
      <h1 className="font-display text-3xl mb-1">Welcome back</h1>
      <p className="text-muted text-sm mb-8">Log in to book tickets or manage your events.</p>

      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="text-xs uppercase tracking-wide text-muted block mb-1.5">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full hairline px-3 py-2.5 bg-surface focus:outline-none focus:border-ink"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-muted block mb-1.5">Password</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full hairline px-3 py-2.5 bg-surface focus:outline-none focus:border-ink"
          />
        </div>

        {error && <p className="text-rust text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-ink text-paper px-5 py-3 text-sm hover:bg-forest transition-colors disabled:opacity-50"
        >
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>

      <p className="text-sm text-muted mt-6">
        Don&rsquo;t have an account?{" "}
        <Link href="/register" className="text-forest hover:underline">
          Sign up
        </Link>
      </p>
    </div>
  );
}
