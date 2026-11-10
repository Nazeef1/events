"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { Booking } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

export default function MyBookingsPage() {
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<Booking[]>("/bookings")
      .then(setBookings)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function cancelBooking(booking: Booking) {
    const { id } = booking;
    const consequence = booking.status === "CONFIRMED" && Number(booking.total_amount) > 0 ? " You will be refunded in full." : "";
    if (!window.confirm(`Cancel this booking?${consequence}`)) return;
    setCancellingId(id);
    try {
      await api.post(`/bookings/${id}/cancel`);
      load();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Could not cancel this booking.");
    } finally {
      setCancellingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="font-display text-3xl mb-8">My bookings</h1>

      {error && <p className="text-rust text-sm">{error}</p>}
      {bookings && bookings.length === 0 && <p className="text-muted text-sm">You haven&rsquo;t booked anything yet.</p>}

      <div className="space-y-px bg-line hairline">
        {bookings?.map((b) => (
          <div key={b.id} className="bg-paper p-5 flex items-center justify-between gap-4">
            <div>
              <p className="font-mono text-xs text-muted mb-1">#{b.id.slice(0, 8)}</p>
              <p className="text-sm">
                {b.items.map((i) => `${i.quantity}× ${i.ticket_type_name}`).join(", ")}
              </p>
              <p className="text-xs text-muted mt-1">₹{Number(b.total_amount).toLocaleString("en-IN")} · {new Date(b.created_at).toLocaleDateString()}</p>
            </div>
            <div className="flex items-center gap-4">
              <StatusPill status={b.status} />
              {b.status === "PENDING_PAYMENT" && (
                <Link href={`/checkout?booking_id=${b.id}`} className="hairline px-3 py-1.5 text-xs hover:bg-ink hover:text-paper transition-colors">
                  Complete payment
                </Link>
              )}
              {(b.status === "CONFIRMED" || b.status === "PENDING_PAYMENT") && (
                <button
                  onClick={() => cancelBooking(b)}
                  disabled={cancellingId === b.id}
                  className="hairline px-3 py-1.5 text-xs hover:bg-rust hover:text-paper hover:border-rust transition-colors disabled:opacity-40"
                >
                  {cancellingId === b.id ? "Cancelling…" : "Cancel"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
