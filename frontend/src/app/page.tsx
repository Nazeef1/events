"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PaginatedEvents } from "@/lib/types";
import { EventCard } from "@/components/event-card";

export default function HomePage() {
  const [events, setEvents] = useState<PaginatedEvents | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<PaginatedEvents>("/events?page=1&page_size=6")
      .then(setEvents)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <section className="mx-auto max-w-6xl px-6 pt-16 pb-14 border-b border-line">
        <p className="font-mono text-xs uppercase tracking-widest text-forest mb-4">Event discovery &amp; ticketing</p>
        <h1 className="font-display text-5xl md:text-6xl leading-[1.05] max-w-2xl">
          Find what&rsquo;s worth showing up for.
        </h1>
        <p className="text-muted mt-5 max-w-lg text-lg">
          Browse live conferences, concerts, and community meetups. Reserve your ticket, pay securely, and get in.
        </p>
        <div className="mt-8 flex gap-3">
          <Link href="/events" className="bg-ink text-paper px-5 py-3 text-sm hover:bg-forest transition-colors">
            Browse events
          </Link>
          <Link href="/register" className="hairline px-5 py-3 text-sm hover:bg-ink hover:text-paper transition-colors">
            Become an organizer
          </Link>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-14">
        <div className="flex items-baseline justify-between mb-6">
          <h2 className="font-display text-2xl">Upcoming events</h2>
          <Link href="/events" className="text-sm text-forest hover:underline">
            View all →
          </Link>
        </div>

        {error && <p className="text-rust text-sm">Could not load events: {error}</p>}
        {!events && !error && <p className="text-muted text-sm">Loading events…</p>}
        {events && events.items.length === 0 && (
          <p className="text-muted text-sm">No published events yet. Check back soon, or create one as an organizer.</p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {events?.items.map((e) => (
            <div key={e.id} className="bg-paper">
              <EventCard event={e} />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
