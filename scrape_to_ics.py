import os
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from icalendar import Calendar, Event

def get_stadium_events():
    """Scrapes Wembley Stadium website events."""
    url = "https://www.wembleystadium.com/events"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching Stadium page: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events_data = []
    
    date_pattern = re.compile(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b')
    time_pattern = re.compile(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b')

    date_nodes = soup.find_all(string=date_pattern)
    
    for node in date_nodes:
        date_str = date_pattern.search(node).group()
        
        parent = node.parent
        context_text = ""
        for _ in range(4): 
            if parent:
                context_text += " " + parent.get_text(separator=" ", strip=True)
                parent = parent.parent
        
        times = time_pattern.findall(context_text)
        event_time = times[0] if times else "19:00"
        
        title = "Wembley Stadium Event"
        current = node.parent
        found_title = False
        
        for _ in range(5):
            if current and not found_title:
                link_or_header = current.find(['a', 'h2', 'h3', 'h4'], class_=lambda c: c and any(x in c.lower() for x in ['title', 'header', 'name']))
                if not link_or_header:
                    link_or_header = current.find(['h3', 'h2', 'a'])
                
                if link_or_header:
                    txt = link_or_header.get_text(strip=True)
                    if txt and len(txt) > 3 and not date_pattern.search(txt) and "event" not in txt.lower():
                        title = txt
                        found_title = True
            if current:
                current = current.parent

        if "Past Events" not in title:
            entry = {
                "title": title,
                "date_str": f"{date_str} {event_time}",
                "is_tbc": len(times) == 0
            }
            if entry not in events_data:
                events_data.append(entry)
                
    return events_data


def add_ovo_arena_events(cal):
    """Scrapes OVO Arena events using text-pattern tracking."""
    url = "https://www.ovoarena.co.uk/events"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"Skipping OVO Arena: Status code {response.status_code}")
            return
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Matches formats like "Fri 26 Jun 2026" or "Friday 26 Jun 2026"
        date_pattern = re.compile(r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\s+\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b')
        
        date_nodes = soup.find_all(string=date_pattern)
        print(f"Scraping OVO Arena... Found {len(date_nodes)} text matches.")
        
        for node in date_nodes:
            date_str = date_pattern.search(node).group()
            
            # Walk up to find the contextual text wrapper block for the title
            parent = node.parent
            context_text = ""
            for _ in range(4):
                if parent:
                    context_text += " " + parent.get_text(separator=" ", strip=True)
                    parent = parent.parent
            
            # Clean up double spacing
            context_text = " ".join(context_text.split())
            
            # Find closest heading or link for the event title
            title = "OVO Arena Event"
            current = node.parent
            found_title = False
            for _ in range(4):
                if current and not found_title:
                    heading = current.find(['h3', 'h2', 'h4', 'a'])
                    if heading:
                        txt = heading.get_text(strip=True)
                        if txt and len(txt) > 3 and not date_pattern.search(txt) and "event" not in txt.lower():
                            title = txt
                            found_title = True
                if current:
                    current = current.parent

            try:
                # Standardize strings like "Friday 26 Jun 2026" to datetime object
                clean_date = " ".join(date_str.split())
                # Truncate weekday long names to 3 letters to keep format standard
                parts = clean_date.split()
                parts[0] = parts[0][:3]
                parsed_date = datetime.strptime(" ".join(parts), "%a %d %b %Y")
            except ValueError:
                continue

            # Standard Arena doors time setup
            start_time = parsed_date.replace(hour=18, minute=30)
            busy_start = start_time - timedelta(hours=1, minutes=30)
            busy_end = start_time + timedelta(hours=3, minutes=30)

            e = Event()
            e.add('summary', f"🎤 [ARENA] {title}")
            e.add('dtstart', busy_start)
            e.add('dtend', busy_end)
            e.add('location', 'OVO Arena Wembley')
            e.add('description', (
                f"LOCAL AREA CONGESTION WARNING\n"
                f"---------------------------\n"
                f"Venue: OVO Arena Wembley\n"
                f"Event: {title}\n\n"
                f"🚨 Medium density crowds expected around the Arena floor and Wembley Park Station."
            ))
            cal.add_component(e)
                
    except Exception as e:
        print(f"Error reading OVO Arena data: {e}")

def generate_ics():
    """The master compilation zone linking the scraping blocks together."""
    cal = Calendar()
    cal.add('prodid', '-//Wembley Local Crowd Alerts//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-caltimezone', 'Europe/London')

    # 1. Run the Stadium block
    print("Scraping Wembley Stadium...")
    stadium_events = get_stadium_events()
    for ev in stadium_events:
        try:
            event_start = datetime.strptime(ev['date_str'], "%d %b %Y %H:%M")
        except ValueError:
            continue

        # --- STADIUM CAPACITY LOGIC (80,000+ people) ---
        # Intense 2.5 Hour pre-event transit lock
        busy_start = event_start - timedelta(hours=2, minutes=30) 
        busy_end = event_start + timedelta(hours=4)

        e = Event()
        e.add('summary', f"⚠️ [STADIUM] {ev['title']}")
        e.add('dtstart', busy_start)
        e.add('dtend', busy_end)
        e.add('location', 'Wembley Stadium & Olympic Way')
        
        tbc_note = " (Time is TBC, applied default 19:00 rule)" if ev['is_tbc'] else ""
        e.add('description', (
            f"EXPECTED AREA TRAFFIC ALERT\n"
            f"---------------------------\n"
            f"Event Name: {ev['title']}\n"
            f"Scheduled Start: {event_start.strftime('%H:%M')}{tbc_note}\n\n"
            f"🚶 Influx Peak (Station packed): {busy_start.strftime('%H:%M')} -> {event_start.strftime('%H:%M')}\n"
            f"🚗 Efflux Peak (Leaving venue): {event_start.strftime('%H:%M')} onwards."
        ))
        cal.add_component(e)

    # 2. RUN ALONGSIDE: Pass the calendar to the OVO Arena parser to inject its entries
    add_ovo_arena_events(cal)

    # Save the file cleanly to the root directory only
    output_path = "wembley_traffic.ics"

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())
        
    print("Successfully compiled calendar data directly to the root directory!")
        
    # Also overwrite the root file so your Github hosted copy changes instantly
    with open("wembley_traffic.ics", "wb") as f_root:
        f_root.write(cal.to_ical())
        
    print("Successfully compiled merged calendar datasets!")

if __name__ == "__main__":
    generate_ics()
