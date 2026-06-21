import os
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from icalendar import Calendar, Event

def get_events():
    url = "https://www.wembleystadium.com/events"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching page: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events_data = []
    
    date_pattern = re.compile(r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b')
    time_pattern = re.compile(r'\b(?:[01]\d|2[0-3]):[0-5]\d\b')

    # Fixed warning by replacing text= with string=
    date_nodes = soup.find_all(string=date_pattern)
    
    for node in date_nodes:
        date_str = date_pattern.search(node).group()
        
        parent = node.parent
        context_text = ""
        for _ in range(4): # Broadened window slightly to pull structural titles
            if parent:
                context_text += " " + parent.get_text(separator=" ", strip=True)
                parent = parent.parent
        
        times = time_pattern.findall(context_text)
        event_time = times[0] if times else "19:00"
        
        # TARGETED EXTRACTION: Look for hyperlinked anchor tags or parent card titles
        title = "Wembley Stadium Event"
        current = node.parent
        found_title = False
        
        for _ in range(5):
            if current and not found_title:
                # Search for typical heading markers or links enclosing text inside the event card
                link_or_header = current.find(['a', 'h2', 'h3', 'h4'], class_=lambda c: c and any(x in c.lower() for x in ['title', 'header', 'name']))
                if not link_or_header:
                    link_or_header = current.find(['h3', 'h2', 'a'])
                
                if link_or_header:
                    txt = link_or_header.get_text(strip=True)
                    # Block out calendar noise or repeating dates as titles
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

def generate_ics():
    events = get_events()
    cal = Calendar()
    cal.add('prodid', '-//Wembley Local Crowd Alerts//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-caltimezone', 'Europe/London')

    for ev in events:
        try:
            event_start = datetime.strptime(ev['date_str'], "%d %b %Y %H:%M")
        except ValueError:
            continue

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

    os.makedirs("www", exist_ok=True)
    output_path = os.path.join("www", "wembley_traffic.ics")

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())
    print(f"Successfully generated {output_path} with structural names!")

if __name__ == "__main__":
    generate_ics()
