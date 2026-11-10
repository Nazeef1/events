"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Booking, EventDetail, TicketType } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

const MAX_PER_TICKET_TYPE = 20; // mirrors the limit enforced by booking-service

function saleStatus(tt: TicketType): string | null {
  const now = Date.now();
  if (now < new Date(tt.sale_starts_at).getTime()) {
    return `On sale ${new Date(tt.sale_starts_at).toLocaleDateString("en-US", { dateStyle: "medium" })}`;
  }
  if (now > new Date(tt.sale_ends_at).getTime()) return "Sales ended";
  return null;
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();

  const [event, setEvent] = useState<EventDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [reserving, setReserving] = useState(false);
  const [reserveError, setReserveError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<EventDetail>(`/events/${id}`)
      .then(setEvent)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) {
    return <div className="mx-auto max-w-3xl px-6 py-20 text-rust">Could not load this event: {error}</div>;
  }
  if (!event) {
    return <div className="mx-auto max-w-3xl px-6 py-20 text-muted text-sm">Loading…</div>;
  }

  const total = event.ticket_types.reduce((sum, tt) => sum + (quantities[tt.id] || 0) * Number(tt.price), 0);
  const anySelected = Object.values(quantities).some((q) => q > 0);

  async function handleReserve() {
    if (!user) {
      router.push(`/login?next=/events/${id}`);
      return;
    }
    setReserveError(null);
    setReserving(true);
    try {
      const items = Object.entries(quantities)
        .filter(([, qty]) => qty > 0)
        .map(([ticket_type_id, quantity]) => ({ ticket_type_id, quantity }));

      const booking = await api.post<Booking>(
        "/bookings/reserve",
        { event_id: event!.id, items },
        { idempotencyKey: `reserve-${event!.id}-${Date.now()}` }
      );
      // Free bookings are confirmed immediately and skip payment.
      router.push(booking.status === "CONFIRMED" ? `/booking/success?booking_id=${booking.id}` : `/checkout?booking_id=${booking.id}`);
    } catch (err) {
      setReserveError(err instanceof ApiError ? err.message : "Could not reserve tickets. Please try again.");
    } finally {
      setReserving(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs uppercase tracking-widest text-muted">{event.category}</span>
        <StatusPill status={event.status} />
      </div>
      <h1 className="font-display text-4xl mb-4">{event.title}</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="md:col-span-2 space-y-8">
          <div className="hairline p-5 grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted mb-1">When</p>
              <p>{new Date(event.starts_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</p>
              <p className="text-muted">to {new Date(event.ends_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted mb-1">Where</p>
              <p>{event.venue_name || "TBA"}</p>
              <p className="text-muted">{event.venue_address}{event.venue_address && event.city ? ", " : ""}{event.city}</p>
            </div>
          </div>

          <div>
            <h2 className="font-display text-xl mb-2">About this event</h2>
            <p className="text-sm leading-relaxed whitespace-pre-wrap text-ink/90">{event.description || "No description provided."}</p>
          </div>
        </div>

        <div className="hairline p-5 h-fit sticky top-24">
          <h2 className="font-display text-lg mb-4">Select tickets</h2>
          {event.ticket_types.length === 0 && <p className="text-sm text-muted">No tickets available for this event.</p>}
          <div className="space-y-4">
            {event.ticket_types.map((tt) => {
              const unavailableReason = saleStatus(tt);
              const maxQuantity = unavailableReason ? 0 : Math.min(tt.quantity_available, MAX_PER_TICKET_TYPE);
              return (
              <div key={tt.id} className="border-b border-line pb-3 last:border-0">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{tt.name}</p>
                    <p className="font-mono text-sm text-forest">{Number(tt.price) === 0 ? "Free" : `₹${Number(tt.price).toLocaleString("en-IN")}`}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setQuantities((q) => ({ ...q, [tt.id]: Math.max(0, (q[tt.id] || 0) - 1) }))}
                      className="hairline w-7 h-7 text-sm hover:bg-ink hover:text-paper transition-colors"
                    >
                      −
                    </button>
                    <span className="font-mono text-sm w-5 text-center">{quantities[tt.id] || 0}</span>
                    <button
                      type="button"
                      disabled={(quantities[tt.id] || 0) >= maxQuantity}
                      onClick={() => setQuantities((q) => ({ ...q, [tt.id]: Math.min(maxQuantity, (q[tt.id] || 0) + 1) }))}
                      className="hairline w-7 h-7 text-sm hover:bg-ink hover:text-paper transition-colors disabled:opacity-30"
                    >
                      +
                    </button>
                  </div>
                </div>
                <p className="text-xs text-muted mt-1">
                  {unavailableReason ?? (tt.quantity_available > 0 ? `${tt.quantity_available} left` : "Sold out")}
                </p>
              </div>
              );
            })}
          </div>

          {anySelected && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-line text-sm">
              <span className="text-muted">Total</span>
              <span className="font-mono">{total === 0 ? "Free" : `₹${total.toLocaleString("en-IN")}`}</span>
            </div>
          )}

          {reserveError && <p className="text-rust text-xs mt-3">{reserveError}</p>}

          <button
            onClick={handleReserve}
            disabled={!anySelected || reserving || event.status !== "PUBLISHED"}
            className="w-full bg-ink text-paper px-4 py-3 text-sm mt-4 hover:bg-forest transition-colors disabled:opacity-40"
          >
            {reserving ? "Reserving…" : "Reserve tickets"}
          </button>
          <p className="text-xs text-muted mt-2 text-center">Your reservation is held for 10 minutes to complete checkout.</p>
        </div>
      </div>
    </div>
  );
}
