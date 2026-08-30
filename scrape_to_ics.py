import hashlib
import json
import re
from datetime import datetime, timedelta, date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dateutil import parser
from icalendar import Calendar, Event
import pytz


UK_TZ = pytz.timezone("Europe/London")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 20

VENUES = {
    "stadium": {
        "name": "Wembley Stadium",
        "prefix": "Stadium",
        "events_url": "https://www.wembleystadium.com/events",
        "base_url": "https://www.wembleystadium.com",
        "location": "Wembley Stadium, London HA9 0WS, UK",
    },
    "ovo": {
        "name": "OVO Arena",
        "prefix": "OVO Arena",
        "events_url": "https://www.ovoarena.co.uk/events/search",
        "base_url": "https://www.ovoarena.co.uk",
        "location": (
            "The OVO Arena, Wembley, Arena Square, Engineers Way, "
            "Wembley Park, Wembley, HA9 0AA, UK"
        ),
    },
}


def clean_text(value):
    """Normalise whitespace and remove surrounding whitespace."""
    if not value:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def absolute_url(url, base_url):
    """Convert relative event URLs to absolute URLs."""
    if not url:
        return ""

    return urljoin(base_url, url)


def flatten_json_ld(data):
    """
    Yield JSON-LD objects from:
      - a single object
      - a list
      - @graph
    """
    if isinstance(data, list):
        for item in data:
            yield from flatten_json_ld(item)

    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                yield from flatten_json_ld(item)
        else:
            yield data


def is_event_schema(item):
    """Return True for Schema.org Event objects."""
    event_type = item.get("@type")

    if isinstance(event_type, list):
        return "Event" in event_type

    return event_type == "Event"


def parse_event_date(date_str):
    """
    Parse an event date safely.

    IMPORTANT:
    Do not remove '-' from the input. ISO dates such as
    2026-09-02T19:00:00+01:00 depend on those hyphens.

    Returns:
        (datetime/date, has_time)
    """
    if not date_str:
        return None, False

    raw = clean_text(date_str)

    # Detect whether the source actually supplied a time.
    has_time = bool(
        re.search(
            r"\b\d{1,2}:\d{2}\b",
            raw,
        )
        or re.search(r"T\d{2}:\d{2}", raw)
        or re.search(r"\d{1,2}\s*(?:am|pm)\b", raw, re.I)
        or re.search(r"[+-]\d{2}:?\d{2}$", raw)
        or raw.endswith("Z")
    )

    # Remove only known textual qualifiers.
    cleaned = re.sub(
        r"\b(?:Doors?\s+open|Doors|Postponed|Rescheduled|TBC)\b",
        "",
        raw,
        flags=re.I,
    )

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|-")

    try:
        dt = parser.isoparse(cleaned)

        if dt.tzinfo is None:
            dt = UK_TZ.localize(dt)
        else:
            dt = dt.astimezone(UK_TZ)

        return dt, has_time

    except (ValueError, TypeError):
        pass

    # Fallback for human-readable dates.
    try:
        dt = parser.parse(cleaned, fuzzy=True)

        if dt.tzinfo is None:
            dt = UK_TZ.localize(dt)
        else:
            dt = dt.astimezone(UK_TZ)

        return dt, has_time

    except (ValueError, TypeError, OverflowError):
        return None, False


def extract_json_ld_events(soup, venue):
    """
    Extract Schema.org Event objects from JSON-LD.

    This handles both direct Event objects and @graph structures.
    """
    events = []

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in flatten_json_ld(data):
            if not is_event_schema(item):
                continue

            title = clean_text(item.get("name"))
            start_date = item.get("startDate")
            event_url = item.get("url", "")

            if not title or not start_date:
                continue

            # Schema.org location handling.
            location = venue["location"]
            location_data = item.get("location")

            if isinstance(location_data, dict):
                location_name = clean_text(location_data.get("name"))

                address = location_data.get("address")

                if isinstance(address, dict):
                    parts = [
                        clean_text(address.get("streetAddress")),
                        clean_text(address.get("addressLocality")),
                        clean_text(address.get("postalCode")),
                    ]

                    parts = [p for p in parts if p]

                    if location_name:
                        location = ", ".join([location_name] + parts)
                    elif parts:
                        location = ", ".join(parts)

                elif location_name:
                    location = location_name

            events.append(
                {
                    "title": f'[{venue["prefix"]}] {title}',
                    "location": location,
                    "url": absolute_url(event_url, venue["base_url"]),
                    "date_raw": str(start_date),
                    "venue": venue["name"],
                }
            )

    return events


def extract_event_links(soup, venue):
    """
    Extract likely event detail links from a listing page.

    Used as a secondary source when JSON-LD is incomplete.
    """
    links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = clean_text(link.get_text(" ", strip=True))

        if not text or len(text) < 3:
            continue

        full_url = absolute_url(href, venue["base_url"])

        # Avoid navigation and generic links.
        if "/events/" not in full_url.lower():
            continue

        links.append((text, full_url))

    # Preserve order while removing duplicates.
    seen = set()
    result = []

    for text, url in links:
        if url in seen:
            continue

        seen.add(url)
        result.append((text, url))

    return result


def fetch_event_page(event_url, venue):
    """
    Fetch an individual event page and attempt to obtain a more
    authoritative Event schema.
    """
    try:
        response = requests.get(
            event_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        events = extract_json_ld_events(soup, venue)

        if events:
            # The event detail page should normally contain one event.
            return events[0]

    except requests.RequestException as exc:
        print(f"    Event page failed: {event_url} ({exc})")

    return None


def fetch_venue_events(venue):
    """
    Fetch all events for a venue.

    Primary:
        JSON-LD from listing page.

    Secondary:
        Event detail pages discovered from listing links.
    """
    print(f"Scraping {venue['name']}...")

    try:
        response = requests.get(
            venue["events_url"],
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  Failed to fetch {venue['events_url']}: {exc}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Primary source: structured data.
    events = extract_json_ld_events(soup, venue)

    print(f"  JSON-LD events found: {len(events)}")

    # Secondary source: discover detail pages.
    links = extract_event_links(soup, venue)

    if links:
        print(f"  Candidate event links: {len(links)}")

    known_urls = {
        event["url"]
        for event in events
        if event.get("url")
    }

    # Only follow links not already represented by JSON-LD.
    #
    # Limit the number of requests so a broken listing page cannot
    # cause an excessive crawl.
    for _, event_url in links:
        if event_url in known_urls:
            continue

        detail_event = fetch_event_page(event_url, venue)

        if detail_event:
            events.append(detail_event)
            known_urls.add(event_url)

    return events


def make_uid(event_data, start_dt):
    """
    Generate a stable UID.

    Venue is included so the same event title/date at two venues
    cannot collide.
    """
    identity = "|".join(
        [
            event_data["venue"],
            clean_text(event_data["title"]).lower(),
            start_dt.isoformat(),
        ]
    )

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]

    return f"{digest}@wembley-smartevents"


def generate_ics(events, filename="wembley_events.ics"):
    print(f"\nGenerating {filename}...")

    cal = Calendar()

    cal.add("prodid", "-//Wembley SmartEvents Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "Wembley Events (Stadium & OVO)")
    cal.add("x-wr-timezone", "Europe/London")

    now = datetime.now(UK_TZ)

    seen = set()
    parsed_events = []

    for event_data in events:
        start_dt, has_time = parse_event_date(event_data.get("date_raw"))

        if not start_dt:
            print(
                "  Skipping invalid date: "
                f"{event_data['title']} "
                f"(raw={event_data.get('date_raw')!r})"
            )
            continue

        dedup_key = (
            event_data["venue"].lower(),
            clean_text(event_data["title"]).lower(),
            start_dt.isoformat(),
        )

        if dedup_key in seen:
            continue

        seen.add(dedup_key)
        parsed_events.append((event_data, start_dt, has_time))

    # Chronological order.
    parsed_events.sort(key=lambda item: item[1])

    for event_data, start_dt, has_time in parsed_events:
        event = Event()

        event.add("uid", make_uid(event_data, start_dt))
        event.add("dtstamp", now)

        event.add("summary", clean_text(event_data["title"]))
        event.add("location", clean_text(event_data["location"]))

        description = (
            f"Venue: {event_data['venue']}\n"
            f"Source date: {event_data['date_raw']}\n"
            f"More info: {event_data['url']}"
        )

        event.add("description", description)

        if has_time:
            event.add("dtstart", start_dt)

            # Traffic-calendar window:
            # start 2.5 hours before the event and end 4 hours after.
            #
            # If you want the calendar to represent the actual event
            # rather than traffic impact, change these to:
            #
            #   event.add("dtstart", start_dt)
            #   event.add("dtend", start_dt + timedelta(hours=3))
            #
            # The original README describes the traffic-window behaviour.
            traffic_start = start_dt - timedelta(hours=2.5)
            traffic_end = start_dt + timedelta(hours=4)

            event["dtstart"] = traffic_start
            event.add("dtend", traffic_end)

        else:
            # Date-only/TBC event.
            event.add("dtstart", start_dt.date())

        cal.add_component(event)

    if not parsed_events:
        raise RuntimeError(
            "No valid events were found. Existing ICS was not overwritten."
        )

    with open(filename, "wb") as output:
        output.write(cal.to_ical())

    print(
        f"Calendar successfully generated with "
        f"{len(parsed_events)} unique events."
    )


def main():
    stadium_events = fetch_venue_events(VENUES["stadium"])
    ovo_events = fetch_venue_events(VENUES["ovo"])

    all_events = stadium_events + ovo_events

    print(
        f"\nTotal events collected: {len(all_events)} "
        f"(Stadium={len(stadium_events)}, OVO={len(ovo_events)})"
    )

    if not all_events:
        print("No events found. Existing calendar was not changed.")
        return

    generate_ics(all_events)


if __name__ == "__main__":
    main()
