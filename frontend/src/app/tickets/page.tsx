"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Booking } from "@/lib/types";

export default function TicketsPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Booking[]>("/bookings")
      .then((all) => setBookings(all.filter((b) => b.status === "CONFIRMED")))
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="font-display text-3xl mb-8">My tickets</h1>

      {error && <p className="text-rust text-sm">{error}</p>}

      {bookings && bookings.length === 0 && <p className="text-muted text-sm">No confirmed tickets yet.</p>}

      <div className="space-y-6">
        {bookings?.map((b) => (
          <div key={b.id} className="hairline flex">
            <div className="px-6 py-6 border-r border-dashed border-line flex flex-col justify-center items-center min-w-[110px]">
              <p className="font-mono text-[10px] text-muted uppercase tracking-widest">Ticket</p>
              <p className="font-display text-lg mt-1">#{b.id.slice(0, 6).toUpperCase()}</p>
            </div>
            <div className="px-6 py-6 flex-1">
              {b.items.map((i) => (
                <p key={i.id} className="text-sm mb-0.5">
                  {i.quantity} × {i.ticket_type_name}
                </p>
              ))}
              <p className="text-xs text-muted mt-2 font-mono">Booking {b.id}</p>
              <p className="text-xs text-muted font-mono">Reservation {b.reservation_id.slice(0, 8)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
