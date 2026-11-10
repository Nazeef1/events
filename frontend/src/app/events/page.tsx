"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { EventCategory, PaginatedEvents } from "@/lib/types";
import { EventCard } from "@/components/event-card";

const CATEGORIES: EventCategory[] = ["MUSIC", "TECH", "BUSINESS", "ARTS", "SPORTS", "FOOD", "COMMUNITY", "OTHER"];

export default function EventsPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<string>("");
  const [city, setCity] = useState("");
  const [page, setPage] = useState(1);
  const [events, setEvents] = useState<PaginatedEvents | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "12" });
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (city) params.set("city", city);

    setLoading(true);
    api
      .get<PaginatedEvents>(`/events?${params.toString()}`)
      .then(setEvents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [q, category, city, page]);

  const totalPages = events ? Math.max(1, Math.ceil(events.total / events.page_size)) : 1;

  return (
    <div className="mx-auto max-w-6xl px-6 py-12">
      <h1 className="font-display text-3xl mb-6">Browse events</h1>

      <div className="hairline p-4 mb-8 flex flex-wrap gap-3">
        <input
          placeholder="Search events…"
          value={q}
          onChange={(e) => {
            setPage(1);
            setQ(e.target.value);
          }}
          className="flex-1 min-w-[200px] hairline px-3 py-2 bg-surface text-sm focus:outline-none focus:border-ink"
        />
        <select
          value={category}
          onChange={(e) => {
            setPage(1);
            setCategory(e.target.value);
          }}
          className="hairline px-3 py-2 bg-surface text-sm focus:outline-none focus:border-ink"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <input
          placeholder="City"
          value={city}
          onChange={(e) => {
            setPage(1);
            setCity(e.target.value);
          }}
          className="hairline px-3 py-2 bg-surface text-sm w-40 focus:outline-none focus:border-ink"
        />
      </div>

      {error && <p className="text-rust text-sm">Could not load events: {error}</p>}
      {loading && <p className="text-muted text-sm">Loading…</p>}
      {events && events.items.length === 0 && !loading && (
        <p className="text-muted text-sm">No events match your filters.</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {events?.items.map((e) => (
          <div key={e.id} className="bg-paper">
            <EventCard event={e} />
          </div>
        ))}
      </div>

      {events && totalPages > 1 && (
        <div className="flex items-center gap-2 justify-center text-sm">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="hairline px-3 py-1.5 disabled:opacity-40">
            Prev
          </button>
          <span className="text-muted font-mono text-xs">
            Page {page} of {totalPages}
          </span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="hairline px-3 py-1.5 disabled:opacity-40">
            Next
          </button>
        </div>
      )}
    </div>
  );
}
