import re
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
        return UK_TZ.localize(dt)
    except (ValueError, TypeError):
        return None

def fetch_wembley_stadium_events():
    print("Scraping Wembley Stadium...")
    events = []
    url = "https://www.wembleystadium.com/events"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Look for event cards, anchor links containing event paths, or structured blocks
        cards = soup.find_all(["div", "article", "li"], class_=re.compile(r"event|card|listing|item", re.I))
        
        # Fallback: if class matching is too strict, look for links pointing to event subpaths
        if not cards:
            cards = soup.find_all("a", href=re.compile(r"/events/", re.I))

        print(f"  Found {len(cards)} potential elements on Wembley Stadium page.")
        seen_titles = set()

        for card in cards:
            # Extract title
            title_el = card.find(["h2", "h3", "h4", "span"]) if hasattr(card, "find") else None
            title = clean_text(title_el.get_text()) if title_el else clean_text(card.get_text() if card.name == 'a' else "")
            
            if not title or len(title) < 4 or "filter" in title.lower() or "wembley" in title.lower():
                continue
                
            if title in seen_titles:
                continue
            seen_titles.add(title)

            # Extract link
            event_url = card.get("href") if card.name == "a" else (card.find("a", href=True)["href"] if card.find("a", href=True) else url)
            if event_url.startswith("/"):
                event_url = f"https://www.wembleystadium.com{event_url}"

            # Extract date if available
            date_el = card.find(class_=re.compile(r"date|time|meta", re.I)) if hasattr(card, "find") else None
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
        
        container = soup.find(class_=re.compile(r"event-list|events-grid|grid", re.I))
        cards = container.find_all("article") if container else soup.find_all("article")
        
        print(f"  Found {len(cards)} event cards on OVO page.")
        seen_titles = set()
        
        for card in cards:
            title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                continue
                
            title = clean_text(title_el.get_text())
            if not title or len(title) < 3 or title in seen_titles:
                continue
            seen_titles.add(title)

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
        
        # If the date couldn't be parsed from the raw text, we skip or handle gracefully
        if not start_dt:
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