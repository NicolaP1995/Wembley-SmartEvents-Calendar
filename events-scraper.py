from icalendar import Calendar, Event
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

def create_wembley_ics():
    cal = Calendar()
    cal.add('prodid', '-//Wembley Park Local Traffic Assistant//EN')
    cal.add('version', '2.0')

    # 1. Fetch and Parse (Simulated logic for Stadium)
    # url = "https://www.wembleystadium.com/events"
    # ... parse dates, titles, and times ...
    
    # 2. Apply your custom formatting rules
    event_title = "[STADIUM] My Chemical Romance"
    event_date = datetime(2026, 7, 10, 17, 0) # July 10, 2026 at 5:00 PM
    
    # Calculate busy zones based on venue type
    busy_start = event_date - timedelta(hours=2.5)
    busy_end = event_date + timedelta(hours=5) # Assuming a 3.5 hour event + 1.5 hour exit

    # 3. Build the ICS Event
    e = Event()
    e.add('summary', event_title)
    e.add('dtstart', busy_start) # Set calendar event to start when crowds start!
    e.add('dtend', busy_end)
    e.add('location', 'Wembley Stadium & Olympic Way')
    e.add('description', (
        f"🔴 TRAFFIC ALERT\n"
        f"Venue: Wembley Stadium\n"
        f"Event Start: {event_date.strftime('%H:%M')}\n"
        f"Expected Olympic Way Peak Influx: {busy_start.strftime('%H:%M')} to {event_date.strftime('%H:%M')}\n"
        f"Expected Station Congestion: High"
    ))
    
    cal.add_component(e)
    
    # 4. Save file to cloud storage (like GitHub Pages or AWS S3) to get a live URL link
    with open('wembley_traffic.ics', 'wb') as f:
        f.write(cal.to_ical())

if __name__ == "__main__":
    create_wembley_ics()