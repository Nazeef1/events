#!/usr/bin/env python3
"""
Populates a running EventSphere with demo events through the public API.

    python scripts/seed_demo.py [http://localhost:8080/api]

Standard library only. Safe to re-run: it stops if the demo organizer exists.
The organizer gets a random password because nobody needs to log in as it.
"""
import json
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080/api"
DEMO_ORGANIZER = "eventsphere-demo-organizer@example.com"

EVENTS = [
    ("Monsoon Indie Nights", "MUSIC", "Mumbai", "Harbour Stage", "Colaba Causeway", 12,
     "Three independent bands, one rooftop, and the first rain of the season.", [("General", 799, 200), ("Front Row", 1999, 30)]),
    ("Bengaluru Cloud Summit", "TECH", "Bengaluru", "Lakeview Convention Centre", "Outer Ring Road", 21,
     "A full day of talks on distributed systems, platform teams, and running software at scale.", [("Delegate", 2499, 400), ("Workshop Pass", 4999, 60)]),
    ("Founders' Breakfast Club", "BUSINESS", "Pune", "The Long Table", "Koregaon Park", 9,
     "An early morning of honest conversation between first-time founders and operators.", [("Seat", 499, 40)]),
    ("Old City Food Walk", "FOOD", "Delhi", "Meet at Jama Masjid Gate 1", "Chandni Chowk", 16,
     "A guided evening through eleven of the lanes and kitchens that made the old city famous.", [("Walker", 1200, 25)]),
    ("Community Clean-Up Morning", "COMMUNITY", "Chennai", "Elliot's Beach", "Besant Nagar", 6,
     "Bring gloves and a friend. Breakfast is on us afterwards.", [("Volunteer", 0, 150)]),
    ("Contemporary Print Fair", "ARTS", "Kolkata", "North Gallery", "Park Street", 33,
     "Forty printmakers from across the country, with live etching demonstrations all weekend.", [("Day Pass", 250, 500), ("Weekend Pass", 400, 200)]),
]


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or "null")


def main() -> int:
    try:
        account = call("POST", "/auth/register", {
            "email": DEMO_ORGANIZER, "full_name": "EventSphere Demo", "password": secrets.token_urlsafe(24), "role": "ORGANIZER",
        })
    except urllib.error.HTTPError as err:
        if err.code == 409:
            print("Demo data already present; nothing to do.")
            return 0
        raise

    token = account["access_token"]
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for title, category, city, venue, address, days_out, description, tickets in EVENTS:
        starts = now + timedelta(days=days_out)
        event = call("POST", "/events", {
            "title": title, "description": description, "category": category, "city": city,
            "venue_name": venue, "venue_address": address,
            "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=4)).isoformat(),
            "ticket_types": [
                {"name": name, "description": "", "price": str(price), "quantity_total": quantity,
                 "sale_starts_at": (now - timedelta(days=1)).isoformat(), "sale_ends_at": starts.isoformat()}
                for name, price, quantity in tickets
            ],
        }, token)
        call("POST", f"/events/{event['id']}/publish", token=token)
        print(f"Published: {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
