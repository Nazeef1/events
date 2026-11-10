"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export function Navbar() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isOrganizerArea = pathname?.startsWith("/organizer");
  const isAdminArea = pathname?.startsWith("/admin");

  return (
    <header className="hairline border-x-0 border-t-0 sticky top-0 z-40 bg-paper/95 backdrop-blur-none">
      <div className="mx-auto max-w-6xl px-6 py-4 flex flex-wrap items-center justify-between gap-y-3">
        <Link href="/" className="font-display text-xl tracking-tight">
          Event<span className="text-forest">Sphere</span>
        </Link>

        <nav className="order-last w-full md:order-none md:w-auto flex items-center gap-5 md:gap-7 text-sm overflow-x-auto whitespace-nowrap">
          <Link href="/events" className={pathname === "/events" ? "text-ink" : "text-muted hover:text-ink"}>
            Browse Events
          </Link>
          {user && (
            <Link href="/my-bookings" className={pathname === "/my-bookings" ? "text-ink" : "text-muted hover:text-ink"}>
              My Bookings
            </Link>
          )}
          {user && (
            <Link href="/tickets" className={pathname === "/tickets" ? "text-ink" : "text-muted hover:text-ink"}>
              My Tickets
            </Link>
          )}
          {user && (user.role === "ORGANIZER" || user.role === "ADMIN") && (
            <Link href="/organizer" className={isOrganizerArea ? "text-ink" : "text-muted hover:text-ink"}>
              Organizer
            </Link>
          )}
          {user && user.role === "ADMIN" && (
            <Link href="/admin" className={isAdminArea ? "text-ink" : "text-muted hover:text-ink"}>
              Admin
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-4 text-sm">
          {user ? (
            <>
              <Link href="/notifications" className="text-muted hover:text-ink">
                Notifications
              </Link>
              <Link href="/profile" className="text-muted hover:text-ink">
                {user.full_name.split(" ")[0]}
              </Link>
              <button
                onClick={() => {
                  logout();
                  router.push("/");
                }}
                className="hairline px-3 py-1.5 hover:bg-ink hover:text-paper transition-colors"
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-muted hover:text-ink">
                Log in
              </Link>
              <Link href="/register" className="hairline px-3 py-1.5 hover:bg-ink hover:text-paper transition-colors">
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
