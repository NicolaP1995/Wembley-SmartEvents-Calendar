import re
import hashlib
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import pytz
from dateutil import parser

# Set the timezone to local UK time
UK_TZ = pytz.timezone("Europe/London")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def clean_text(text):
    """Strips excessive whitespace and newlines from scraped text."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def parse_event_date(date_str):
    """
    Attempts to parse a variety of messy scraped date formats into a timezone-aware datetime object.
    Returns None if parsing fails entirely.
    """
    if not date_str:
        return None
        
    # Clean up common text phrases that trip up the date parser
    clean_str = re.sub(r"(?i)(Doors open|Doors|from|to|TBC|Postponed|Rescheduled|-.*)", "", date_str).strip()
    
    try:
        # fuzzy=True allows the parser to ignore unrecognized words
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
        
        # Stadium layout heuristic: Find event containers
        cards = soup.find_all(["div", "article", "li"], class_=re.compile(r"event|card|listing", re.I))
        
        for card in cards:
            title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                continue
                
            title = clean_text(title_el.get_text())
            if not title:
                continue

            link_el = card.find("a", href=True)
            event_url = link_el["href"] if link_el else url
            if event_url.startswith("/"):
                event_url = f"https://www.wembleystadium.com{event_url}"

            # Target common date elements
            date_el = card.find(class_=re.compile(r"date|time", re.I))
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
        
        # OVO layout heuristic: Find event containers
        cards = soup.find_all(["article", "div"], class_=re.compile(r"event|card|item", re.I))
        
        for card in cards:
            title_el = card.find(["h2", "h3", "h4"])
            if not title_el:
                continue
                
            title = clean_text(title_el.get_text())
            # Skip empty or generic site navigation headers that get caught
            if not title or len(title) < 3:
                continue

            link_el = card.find("a", href=True)
            event_url = link_el["href"] if link_el else url
            if event_url.startswith("/"):
                event_url = f"https://www.ovoarena.co.uk{event_url}"

            # Grab date
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
    print(f"\nGenerating {filename} with {len(events)} total events...")
    
    cal = Calendar()
    cal.add('prodid', '-//Wembley SmartEvents Calendar//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', 'Wembley Events (Stadium & OVO)')
    cal.add('x-wr-timezone', 'Europe/London')
    cal.add('refresh-interval', 'PT12H') # Suggests calendar clients refresh every 12 hours

    parsed_count = 0

    for event_data in events:
        start_dt = parse_event_date(event_data['date_raw'])
        
        if not start_dt:
            print(f"  [Warning] Could not parse date '{event_data['date_raw']}' for '{event_data['title']}'. Skipping.")
            continue
            
        event = Event()
        event.add('summary', event_data['title'])
        event.add('location', event_data['location'])
        event.add('description', f"Venue: {event_data['venue']}\nRaw Scraped Date: {event_data['date_raw']}\nMore info: {event_data['url']}")
        
        # Generate a consistent, unique ID based on title and date so updates don't create duplicates
        uid_hash = hashlib.md5(f"{event_data['title']}{event_data['date_raw']}".encode('utf-8')).hexdigest()
        event.add('uid', f"{uid_hash}@wembley-smartevents")
        
        # If no time was provided (it parsed as exactly midnight), treat it as an all-day event
        if start_dt.hour == 0 and start_dt.minute == 0:
            event.add('dtstart', start_dt.date())
        else:
            event.add('dtstart', start_dt)
            # Default the end time to 3 hours later for standard concerts/matches
            event.add('dtend', start_dt + timedelta(hours=3))

        cal.add_component(event)
        parsed_count += 1

    with open(filename, 'wb') as f:
        f.write(cal.to_ical())
        
    print(f"Calendar successfully generated with {parsed_count} valid events!")

if __name__ == "__main__":
    stadium_events = fetch_wembley_stadium_events()
    print(f"-> Found {len(stadium_events)} elements at Wembley Stadium.")
    
    ovo_events = fetch_ovo_arena_events()
    print(f"-> Found {len(ovo_events)} elements at OVO Arena.")
    
    all_events = stadium_events + ovo_events
    
    if all_events:
        generate_ics(all_events)
    else:
        print("No events found across both venues. ICS not generated.")