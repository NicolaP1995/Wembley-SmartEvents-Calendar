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

    event_containers = soup.find_all(['article', 'div'], class_=lambda c: c and any(x in c.lower() for x in ['card', 'event', 'row']))
    
    for container in event_containers:
        text = container.get_text(separator=" ", strip=True)
        dates = date_pattern.findall(text)
        times = time_pattern.findall(text)
        
        title_tag = container.find(['h2', 'h3', 'h4'])
        title = title_tag.get_text(strip=True) if title_tag else None

        if dates and title:
            event_time = times[0] if times else "19:00" 
            events_data.append({
                "title": title,
                "date_str": f"{dates[0]} {event_time}",
                "is_tbc": len(times) == 0
            })
            
    return events_data

def generate_ics():
    events = get_events()
    cal = Calendar()
    cal.add('prodid', '-//Wembley Local Crowd Alerts//EN')
    cal.add('version', '2.0')

    for ev in events:
        try:
            event_start = datetime.strptime(ev['date_str'], "%d %b %Y %H:%M")
        except ValueError:
            continue

        # Buffer windows
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

    # Ensure a local directory named 'www' exists to hold our calendar file
    os.makedirs("www", exist_ok=True)
    output_path = os.path.join("www", "wembley_traffic.ics")

    with open(output_path, "wb") as f:
        f.write(cal.to_ical())
    print(f"Successfully generated {output_path}!")

if __name__ == "__main__":
    generate_ics()