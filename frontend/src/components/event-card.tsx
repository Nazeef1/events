import Link from "next/link";
import type { EventSummary } from "@/lib/types";

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function EventCard({ event }: { event: EventSummary }) {
  const priceLabel =
    event.min_price == null || (Number(event.min_price) === 0 && Number(event.max_price) === 0)
      ? "Free"
      : event.min_price === event.max_price
      ? `₹${Number(event.min_price).toLocaleString("en-IN")}`
      : `From ₹${Number(event.min_price).toLocaleString("en-IN")}`;

  return (
    <Link href={`/events/${event.id}`} className="group block hairline ticket-notch-right">
      <div className="flex">
        <div className="flex flex-col items-center justify-center px-5 py-6 border-r border-dashed border-line min-w-[92px] text-center">
          <span className="font-mono text-xs uppercase tracking-widest text-muted">{formatDate(event.starts_at).split(" ")[0]}</span>
          <span className="font-display text-2xl leading-none mt-1">{new Date(event.starts_at).getDate()}</span>
          <span className="font-mono text-xs text-muted mt-1">{formatDate(event.starts_at).split(" ").slice(1).join(" ")}</span>
        </div>
        <div className="flex-1 px-5 py-6">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-widest text-muted">{event.category}</span>
            <span className="font-mono text-sm text-forest">{priceLabel}</span>
          </div>
          <h3 className="font-display text-lg mt-1.5 group-hover:text-forest transition-colors">{event.title}</h3>
          <p className="text-sm text-muted mt-1">
            {event.city || "Location TBA"} · {formatTime(event.starts_at)}
          </p>
        </div>
      </div>
    </Link>
  );
}
