"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface PlatformSummary {
  total_events_tracked: number;
  total_views: number;
  total_bookings_confirmed: number;
  total_tickets_sold: number;
  total_revenue: number;
}

export default function AdminAnalyticsPage() {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<PlatformSummary>("/analytics/platform/summary").then(setSummary).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="mx-auto max-w-3xl px-6 py-20 text-rust text-sm">{error}</div>;
  if (!summary) return <div className="mx-auto max-w-3xl px-6 py-20 text-muted text-sm">Loading…</div>;

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="font-display text-3xl mb-8">Platform analytics</h1>
      {/* Five tiles: the last one spans two columns so no empty cell shows in either layout. */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-line hairline [&>*:last-child]:col-span-2">
        <Metric label="Events tracked" value={summary.total_events_tracked} />
        <Metric label="Total views" value={summary.total_views} />
        <Metric label="Confirmed bookings" value={summary.total_bookings_confirmed} />
        <Metric label="Tickets sold" value={summary.total_tickets_sold} />
        <Metric label="Platform revenue" value={`₹${summary.total_revenue.toLocaleString("en-IN")}`} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-paper p-5">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className="font-display text-2xl mt-1">{value}</p>
    </div>
  );
}
