"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Script from "next/script";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { Booking, Payment } from "@/lib/types";

interface CreateOrderResponse {
  razorpay_order_id: string;
  razorpay_key_id: string;
  amount_paise: number;
  currency: string;
  booking_id: string;
  mode: "razorpay" | "mock";
}

type Stage = "review" | "processing" | "mock" | "success" | "failed" | "expired";

declare global {
  interface Window {
    Razorpay: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-lg px-6 py-20 text-muted text-sm">Loading…</div>}>
      <CheckoutContent />
    </Suspense>
  );
}

function CheckoutContent() {
  const params = useSearchParams();
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const bookingId = params.get("booking_id");

  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("review");
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [mockOrderId, setMockOrderId] = useState<string | null>(null);

  useEffect(() => {
    if (!bookingId) return;
    api
      .get<Booking>(`/bookings/${bookingId}`)
      .then((b) => {
        setBooking(b);
        if (b.status === "EXPIRED" || b.status === "CANCELLED") setStage("expired");
        if (b.status === "CONFIRMED") setStage("success");
      })
      .catch((e) => setError(e.message));
  }, [bookingId]);

  useEffect(() => {
    if (!booking?.expires_at) return;
    const tick = () => {
      const remaining = Math.max(0, Math.floor((new Date(booking.expires_at!).getTime() - Date.now()) / 1000));
      setSecondsLeft(remaining);
      if (remaining <= 0 && stage === "review") setStage("expired");
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [booking, stage]);

  const startPayment = useCallback(async () => {
    if (!booking) return;
    setStage("processing");
    setError(null);
    try {
      const order = await api.post<CreateOrderResponse>("/payments/order", { booking_id: booking.id });

      if (order.mode === "mock") {
        setMockOrderId(order.razorpay_order_id);
        setStage("mock");
        return;
      }
      if (!window.Razorpay) {
        setError("The payment gateway could not be loaded. Check your connection and try again.");
        setStage("review");
        return;
      }

      const options = {
        key: order.razorpay_key_id,
        amount: order.amount_paise,
        currency: order.currency,
        name: "EventSphere",
        description: `Booking ${booking.id.slice(0, 8)}`,
        order_id: order.razorpay_order_id,
        prefill: { name: user?.full_name, email: user?.email },
        theme: { color: "#1F5E45" },
        handler: async (response: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
          try {
            await api.post<Payment>("/payments/verify", response);
            setStage("success");
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Payment verification failed.");
            setStage("failed");
          }
        },
        modal: {
          ondismiss: () => setStage("review"),
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.open();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start payment. Please try again.");
      setStage("review");
    }
  }, [booking, user]);

  const completeMockPayment = useCallback(async () => {
    setStage("processing");
    try {
      const signed = await api.post<Record<string, string>>("/payments/mock-pay", { razorpay_order_id: mockOrderId });
      await api.post<Payment>("/payments/verify", signed);
      setStage("success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Payment verification failed.");
      setStage("failed");
    }
  }, [mockOrderId]);

  if (authLoading) return null;
  if (!bookingId) return <div className="mx-auto max-w-lg px-6 py-20 text-muted text-sm">No booking specified.</div>;
  if (error && !booking) return <div className="mx-auto max-w-lg px-6 py-20 text-rust text-sm">{error}</div>;
  if (!booking) return <div className="mx-auto max-w-lg px-6 py-20 text-muted text-sm">Loading your order…</div>;

  const minutes = secondsLeft != null ? Math.floor(secondsLeft / 60) : null;
  const seconds = secondsLeft != null ? secondsLeft % 60 : null;

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <Script src="https://checkout.razorpay.com/v1/checkout.js" />

      <h1 className="font-display text-3xl mb-1">Checkout</h1>
      <p className="text-muted text-sm mb-8">Review your order and complete payment.</p>

      <div className="hairline p-5 mb-6">
        {booking.items.map((item) => (
          <div key={item.id} className="flex justify-between text-sm py-1.5">
            <span>
              {item.quantity} × {item.ticket_type_name}
            </span>
            <span className="font-mono">₹{(Number(item.unit_price) * item.quantity).toLocaleString("en-IN")}</span>
          </div>
        ))}
        <div className="flex justify-between text-sm pt-3 mt-3 border-t border-line font-medium">
          <span>Total</span>
          <span className="font-mono">₹{Number(booking.total_amount).toLocaleString("en-IN")}</span>
        </div>
      </div>

      {stage === "review" && secondsLeft != null && secondsLeft > 0 && (
        <p className="text-xs text-gold font-mono mb-4 text-center">
          Reservation held for {minutes}:{String(seconds).padStart(2, "0")}
        </p>
      )}

      {stage === "review" && error && <p className="text-rust text-sm mb-4 text-center">{error}</p>}

      {stage === "review" && (
        <button onClick={startPayment} className="w-full bg-ink text-paper px-5 py-3 text-sm hover:bg-forest transition-colors">
          Proceed to payment
        </button>
      )}

      {stage === "mock" && (
        <div className="hairline p-5 text-center">
          <p className="font-mono text-xs uppercase tracking-widest text-gold mb-2">Simulated payment</p>
          <p className="text-sm text-muted mb-4">Payment simulator is on. No real money will move.</p>
          <div className="flex gap-3 justify-center">
            <button onClick={completeMockPayment} className="bg-ink text-paper px-5 py-2.5 text-sm hover:bg-forest transition-colors">
              Complete test payment
            </button>
            <button onClick={() => setStage("review")} className="hairline px-5 py-2.5 text-sm hover:bg-ink hover:text-paper transition-colors">
              Cancel
            </button>
          </div>
        </div>
      )}

      {stage === "processing" && <p className="text-center text-sm text-muted">Payment processing…</p>}

      {stage === "failed" && (
        <div className="text-center">
          <p className="text-rust text-sm mb-4">{error || "Payment failed."}</p>
          <button onClick={() => setStage("review")} className="hairline px-5 py-2.5 text-sm hover:bg-ink hover:text-paper transition-colors">
            Try again
          </button>
        </div>
      )}

      {stage === "expired" && (
        <div className="text-center">
          <p className="text-rust text-sm mb-4">Your reservation expired or was cancelled before payment.</p>
          <button onClick={() => router.push("/events")} className="hairline px-5 py-2.5 text-sm hover:bg-ink hover:text-paper transition-colors">
            Browse events again
          </button>
        </div>
      )}

      {stage === "success" && (
        <div className="text-center">
          <p className="text-forest text-sm mb-4">Payment successful. Your booking is confirmed.</p>
          <button
            onClick={() => router.push(`/booking/success?booking_id=${booking.id}`)}
            className="bg-ink text-paper px-5 py-2.5 text-sm hover:bg-forest transition-colors"
          >
            View confirmation
          </button>
        </div>
      )}
    </div>
  );
}
