from bs4 import BeautifulSoup
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import re

def get_timezone_offsets(timezone_str):
    tz = pytz.timezone(timezone_str)
    now = datetime.now()
    dt_std = datetime(now.year, 1, 1)
    dt_dst = datetime(now.year, 7, 1)
    
    offset_std = tz.utcoffset(dt_std).total_seconds()
    offset_dst = tz.utcoffset(dt_dst).total_seconds()
    
    offset_std = timedelta(seconds=offset_std)
    offset_dst = timedelta(seconds=offset_dst)
    
    return offset_std, offset_dst

def format_offset(offset):
    hours, remainder = divmod(int(offset.total_seconds()), 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours:+03d}{minutes:02d}"

def parse_html_to_ics(html_file_path, ics_file_path):
    with open(html_file_path, 'r', encoding='utf-8') as file:
        soup = BeautifulSoup(file, 'html.parser')
    
    # Extract the marquee section header for the calendar name
    marquee_header = soup.find('div', {'class': 'marquee__content'}).find('h1')
    calendar_name = marquee_header.get_text(strip=True) if marquee_header else 'TAK Offsite 2024'
    
    # Mapping of timezone abbreviations to their full names
    timezone_map = {
        'MDT': 'America/Denver',
        'PDT': 'America/Los_Angeles',
        'EDT': 'America/New_York',
        'CDT': 'America/Chicago',
        # Add more mappings as needed
    }
    
    # Find the schedule content
    schedule_content = soup.find('div', {'class': 'tab-content', 'id': 'schedules-content'})
    
    if not schedule_content:
        print("Schedule content not found")
        return
    
    events_dict = {}
    time_re = re.compile(r'\d{2}:\d{2} (\w{3})')
    
    # Extract timezone abbreviation from the event times
    timezone_abbreviation = None
    for time_cell in schedule_content.find_all('td', {'class': 'event-grid-time'}):
        time_text = time_cell.get_text(strip=True)
        match = time_re.search(time_text)
        if match:
            timezone_abbreviation = match.group(1)
            break
    
    timezone_str = timezone_map.get(timezone_abbreviation, 'America/Denver')
    offset_std, offset_dst = get_timezone_offsets(timezone_str)
    
    tzoffsetfrom_std = format_offset(offset_std)
    tzoffsetto_dst = format_offset(offset_dst)
    
    # Helper function to identify day number from day string
    def identify_day(day_str):
        if "July 9th" in day_str:
            return 1
        elif "July 10th" in day_str:
            return 2
        elif "July 11th" in day_str:
            return 3
        return None

    # Helper function to add minutes to a time string
    def add_minutes_to_time(time_str, minutes):
        time_obj = datetime.strptime(time_str, "%H:%M")
        new_time = time_obj + timedelta(minutes=minutes)
        return new_time.strftime("%H:%M")
    
    # Helper function to extract the category from the column header
    def extract_category_from_header(header):
        if '-' in header:
            return header.split('-', 1)[1].strip()
        return header

    # Timezone for the events
    tz = pytz.timezone(timezone_str)
    
    # Mapping for day start columns
    day_start_columns = {
        1: 0,  # Day 1 starts at column 0
        2: 1,  # Day 2 starts at column 1
        3: 4   # Day 3 starts at column 4
    }
    
    # Mapping for locations based on track for each day
    location_map = {
        1: ['Salon A'],
        2: ['Salon A', 'Salon B', 'Salon C'],
        3: ['Salon A', 'Salon B', 'Salon C']
    }
    
    # Mapping for tracks for each day
    track_map = {
        1: ['Plenary Sessions'],
        2: ['General Sessions', 'Plenary Sessions', 'Multiple Tracks'],
        3: ['Program Sessions', 'Panel Discussions', 'Architecture Sessions']
    }
    
    # Iterate over each day's schedule grid
    for day_section in schedule_content.find_all('div', {'class': 'col-12 schedule-grid'}):
        day_header = day_section.find('h3')
        if not day_header:
            continue
        
        day_name = day_header.get_text(strip=True)
        day_number = identify_day(day_name)
        if day_number is None:
            continue
        
        start_col_index = day_start_columns.get(day_number, 0)
        locations = location_map.get(day_number, [])
        tracks = track_map.get(day_number, [])
        
        # Find the table and process each row
        table = day_section.find('table')
        if not table:
            continue
        
        rows = table.find_all('tr')
        
        for row in rows[2:]:
            time_cell = row.find('td', {'class': 'event-grid-time'})
            if not time_cell:
                continue
            
            time_text = time_cell.get_text(strip=True)
            match = time_re.search(time_text)
            if not match:
                continue
            
            col_index = start_col_index  # Reset column index for each row
            event_cells = row.find_all('td')[1:]  # Skip the first time cell
            for event_cell in event_cells:
                rowspan = event_cell.get('rowspan')
                if rowspan:
                    event_info = event_cell.find('div', {'class': 'event-grid-event-content'})
                    if event_info:
                        event_link = event_info.find('a')
                        if event_link:
                            event_name = event_link.get_text(strip=True)
                            event_href = event_link['href']
                            if col_index - start_col_index < len(tracks):
                                track = tracks[col_index - start_col_index]
                                location = locations[col_index - start_col_index]
                            else:
                                track = 'Unknown'
                                location = 'Unknown'
                            category = extract_category_from_header(track)
                            duration_minutes = int(rowspan) * 15
                            end_time_str = add_minutes_to_time(time_text[:5], duration_minutes)
                            
                            # Correctly locate event tags
                            event_tags = event_cell.find_all('span', class_='event-grid-event-tag')
                            tags = [tag.get_text(strip=True) for tag in event_tags]
                            
                            event_key = (event_name)  # Simplified key for de-duplication
                            if event_key not in events_dict:
                                start_time = datetime.strptime(f"2024-07-{day_number + 8} {time_text[:5]}", "%Y-%m-%d %H:%M")
                                start_time = tz.localize(start_time)
                                end_time = datetime.strptime(f"2024-07-{day_number + 8} {end_time_str}", "%Y-%m-%d %H:%M")
                                end_time = tz.localize(end_time)
                                
                                events_dict[event_key] = {
                                    'name': event_name,
                                    'start_time': start_time,
                                    'end_time': end_time,
                                    'track': track,
                                    'location': location,
                                    'link': event_href,
                                    'categories': [category] + tags
                                }
                            else:
                                # Update the location for deduplicated events
                                events_dict[event_key]['location'] = 'All Salons'
                col_index += 1  # Increment column index for next cell
    
    # Create the .ics file
    calendar = Calendar()
    ics_events = []
    
    for event in events_dict.values():
        e = Event()
        e.name = event['name']
        e.begin = event['start_time']
        e.end = event['end_time']
        e.location = event['location']
        e.description = f"Track: {event['track']}\nLink: {event['link']}"
        e.categories = event['categories']
        calendar.events.add(e)
        
        # Manually create event strings
        dtstart = event['start_time'].strftime("%Y%m%dT%H%M%S")
        dtend = event['end_time'].strftime("%Y%m%dT%H%M%S")
        
        ics_event = (
            "BEGIN:VEVENT\n"
            f"SUMMARY:{e.name}\n"
            f"DTSTART;TZID={timezone_str}:{dtstart}\n"
            f"DTEND;TZID={timezone_str}:{dtend}\n"
            f"DESCRIPTION:{e.description}\n"
            f"LOCATION:{e.location}\n"
            f"CATEGORIES:{','.join(e.categories)}\n"
            "END:VEVENT"
        )
        ics_events.append(ics_event)
    
    # Add the custom header
    header = (
        "BEGIN:VCALENDAR\n"
        "VERSION:2.0\n"
        "PRODID:-//TAK Product Center//EN\n"
        "CALSCALE:GREGORIAN\n"
        "METHOD:PUBLISH\n"
        f"X-WR-CALNAME:{calendar_name}\n"
        f"X-WR-TIMEZONE:{timezone_str}\n"
    )
    
    # Add the VTIMEZONE component
    vtimezone = (
        "BEGIN:VTIMEZONE\n"
        f"TZID:{timezone_str}\n"
        "BEGIN:STANDARD\n"
        "DTSTART:19710101T020000\n"
        "RRULE:FREQ=YEARLY;BYDAY=1SU;BYMONTH=11\n"
        f"TZOFFSETFROM:{tzoffsetto_dst}\n"
        f"TZOFFSETTO:{tzoffsetfrom_std}\n"
        "END:STANDARD\n"
        "BEGIN:DAYLIGHT\n"
        "DTSTART:19710311T020000\n"
        "RRULE:FREQ=YEARLY;BYDAY=2SU;BYMONTH=3\n"
        f"TZOFFSETFROM:{tzoffsetfrom_std}\n"
        f"TZOFFSETTO:{tzoffsetto_dst}\n"
        "END:DAYLIGHT\n"
        "END:VTIMEZONE"
    )
    
    final_ics_content = f"{header}\n{vtimezone}\n" + "\n\n".join(ics_events) + "\nEND:VCALENDAR"
    
    # Write the content to the file with the correct line endings
    with open(ics_file_path, 'w', encoding='utf-8', newline='\n') as file:
        file.write(final_ics_content)
    
    print(f"ICS file created at {ics_file_path}")

# Specify the input HTML file and output ICS file paths
html_file_path = './2024_Offsite.html'
ics_file_path = './TAK_Offsite_2024_Schedule.ics'

# Parse the HTML and create the ICS file
parse_html_to_ics(html_file_path, ics_file_path)
