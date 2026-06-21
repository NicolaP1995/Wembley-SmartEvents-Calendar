# Wembley SmartEvents Calendar 📅

An automated Python scraping script running on a Raspberry Pi that generates a custom `.ics` calendar tracking Wembley Stadium events. 

### Why this exists:
Standard Wembley event calendars only provide generic "All Day" blocks. This script automatically parses event layouts and injects custom **2.5-hour pre-event influx** and **4-hour post-event efflux** traffic alert windows. This allows locals to know exactly when Olympic Way and Wembley Park Station will be congested.

## Features
- 🚨 **Accurate Crowding Windows:** Shifts calendar events to reflect local traffic impact rather than just event start times.
- 🏟️ **Venue Filtering:** Clearly prefixes locations (e.g., `[STADIUM]`).
- 🤖 **Fully Automated:** Runs daily via a local system `cron` job on a Raspberry Pi.
