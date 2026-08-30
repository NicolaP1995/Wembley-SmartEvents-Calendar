import re
import json
import hashlib
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import pytz
from dateutil import parser

UK_TZ = pytz.timezone("Europe/London")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def parse_event_date(date_str):
    if not date_str:
        return None
    clean_str = re.sub(r"(?i)(Doors open|Doors|from|to|TBC|Postponed|Rescheduled|-.*)", "", date_str).strip()
    try:
        dt = parser.parse(clean_str, fuzzy=True)
        if dt.tzinfo is None:
            return UK_TZ.localize(dt)
        return dt.astimezone(UK_TZ)
    except (ValueError, TypeError):
        return None

def extract_json_ld_events(soup, venue_prefix, default_location, venue_name):
    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.text)
            # Handle list of schemas or single schema
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Event" or (isinstance(item.get("@type"), list) and "Event" in item.get("@type")):
                    title = item.get("name")
                    start_date = item.get("startDate")
                    url = item.get("url", "")
                    
                    loc_data = item.get("location", {})
                    location = default_location
                    if isinstance(loc_data, dict):
                        loc_name = loc_data.get("name")
                        address = loc_data.get("address")
                        if isinstance(address, dict):
                            street = address.get("streetAddress", "")
                            locality = address.get("addressLocality", "")
                            postal = address.get("postalCode", "")
                            location = f"{loc_name}, {street}, {locality} {postal}".strip(", ")
                        elif loc_name:
                            location = loc_name

                    if title and start_date:
                        events.append({
                            "title": f"[{venue_prefix}] {clean_text(title)}",
                            "location": location,
                            "url": url,
                            "date_raw": start_date,
                            "venue": venue_name
                        })
        except Exception:
            continue
    return events

def fetch_wembley_stadium_events():
    print("Scraping Wembley Stadium...")
    events = []
    url = "https://www.wembleystadium.com/events"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Try JSON-LD structured data first (most reliable)
        events = extract_json_ld_events(soup, "Stadium", "Wembley Stadium, London HA9 0WS, UK", "Wembley Stadium")
        print(f"  Found {len(events)} events via JSON-LD on Stadium page.")
        
        # 2. Fallback to HTML card parsing if JSON-LD isn't present
        if not events:
            cards = soup.find_all(["div", "article", "li", "a"], class_=re.compile(r"event|card|item|listing", re.I))
            print(f"  Found {len(cards)} raw elements via HTML fallback.")
            
            for card in cards:
                title_el = card.find(["h2", "h3", "h4", "span"]) if card.name != "a" else card
                title = clean_text(title_el.get_text()) if title_el else ""
                
                if not title or len(title) < 4 or "filter" in title.lower() or "wembley stadium" in title.lower():
                    continue

                link_el = card if card.name == "a" else card.find("a", href=True)
                event_url = link_el["href"] if link_el else url
                if event_url.startswith("/"):
                    event_url = f"https://www.wembleystadium.com{event_url}"

                date_el = card.find(class_=re.compile(r"date|time|meta", re.I))
                date_str = clean_text(date_el.get_text()) if date_el else ""

                events.append({
                    "title": f"[Stadium] {title}",
                    "location": "Wembley Stadium, London HA9 0WS, UK",
                    "url": event_url,
                    "date_raw": date_str,
                    "venue": "Wembley Stadium"
                })
    except Exception as e:
        print(f"Error fetching Wembley Stadium: {e}")
        
    return events

def fetch_ovo_arena_events():
    print("Scraping OVO Arena Wembley...")
    events = []
    url = "https://www.ovoarena.co.uk/events"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 1. Try JSON-LD structured data first
        events = extract_json_ld_events(soup, "OVO Arena", "OVO Arena Wembley, Arena Square, Engineers Way, London HA9 0AA, UK", "OVO Arena")
        print(f"  Found {len(events)} events via JSON-LD on OVO page.")
        
        # 2. Fallback to HTML card parsing
        if not events:
            cards = soup.find_all("article")
            print(f"  Found {len(cards)} raw cards via HTML fallback.")
            
            for card in cards:
                title_el = card.find(["h2", "h3", "h4"])
                if not title_el:
                    continue
                    
                title = clean_text(title_el.get_text())
                if not title or len(title) < 3:
                    continue

                link_el = card.find("a", href=True)
                event_url = link_el["href"] if link_el else url
                if event_url.startswith("/"):
                    event_url = f"https://www.ovoarena.co.uk{event_url}"

                date_el = card.find(class_=re.compile(r"date|time|day|month", re.I))
                date_str = clean_text(date_el.get_text()) if date_el else ""

                events.append({
                    "title": f"[OVO Arena] {title}",
                    "location": "OVO Arena Wembley, Arena Square, Engineers Way, London HA9 0AA, UK",
                    "url": event_url,
                    "date_raw": date_str,
                    "venue": "OVO Arena"
                })
    except Exception as e:
        print(f"Error fetching OVO Arena: {e}")
        
    return events

def generate_ics(events, filename="wembley_events.ics"):
    print(f"\nGenerating {filename}...")
    
    cal = Calendar()
    cal.add('prodid', '-//Wembley SmartEvents Calendar//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', 'Wembley Events (Stadium & OVO)')
    cal.add('x-wr-timezone', 'Europe/London')

    parsed_count = 0
    seen_events = set()

    for event_data in events:
        start_dt = parse_event_date(event_data['date_raw'])
        
        if not start_dt:
            print(f"  Skipping (Invalid date): {event_data['title']} (Raw: {event_data['date_raw']})")
            continue
            
        dedup_key = (event_data['title'].lower(), start_dt.strftime('%Y-%m-%d'))
        if dedup_key in seen_events:
            continue
        seen_events.add(dedup_key)
            
        event = Event()
        event.add('summary', event_data['title'])
        event.add('location', event_data['location'])
        event.add('description', f"Venue: {event_data['venue']}\nRaw Date: {event_data['date_raw']}\nMore info: {event_data['url']}")
        
        uid_hash = hashlib.md5(f"{event_data['title']}{event_data['date_raw']}".encode('utf-8')).hexdigest()
        event.add('uid', f"{uid_hash}@wembley-smartevents")
        
        if start_dt.hour == 0 and start_dt.minute == 0:
            event.add('dtstart', start_dt.date())
        else:
            event.add('dtstart', start_dt)
            event.add('dtend', start_dt + timedelta(hours=3))

        cal.add_component(event)
        parsed_count += 1

    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
        
    print(f"Calendar successfully generated with {parsed_count} unique valid events!")

if __name__ == "__main__":
    stadium_events = fetch_wembley_stadium_events()
    ovo_events = fetch_ovo_arena_events()
    
    all_events = stadium_events + ovo_events
    
    if all_events:
        generate_ics(all_events)
    else:
        print("No events found across both venues. ICS not generated.")