#!/usr/bin/env python3
"""
generate.py — Refreshes the THC Fleet Map from Obsidian vault data.
Replaces the bash generate.sh with a more reliable Python version.
"""

import os
import re
import glob
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
VAULT = "/thc-vault"
HELIS_DIR = f"{VAULT}/Helicopters"
PILOTS_DIR = f"{VAULT}/Pilots"
FLIGHTS_FILE = f"{VAULT}/Flights Schedule.md"
MISSIONS_DIR = f"{VAULT}/Missions"
# Template is index.html itself
HTML_FILE = "/willy/FleetMapAndTimeline/index.html"

TODAY = datetime.now()
TODAY_DISPLAY = TODAY.strftime("%-d %b %Y")
TODAY_YM = TODAY.strftime("%Y-%m")
NEXT_MONTH = (TODAY.replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
THIS_MONTH_NAME = TODAY.strftime("%B")
NEXT_MONTH_NAME = (TODAY.replace(day=1) + timedelta(days=32)).strftime("%B")

def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file."""
    data = {}
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                for line in frontmatter.split('\n'):
                    if ':' in line and not line.strip().startswith('-'):
                        key, val = line.split(':', 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        data[key] = val
    except Exception as e:
        print(f"  Warning: Could not parse {filepath}: {e}")
    return data

def get_helicopters():
    """Read all helicopter data from Obsidian."""
    helicopters = []
    for f in sorted(glob.glob(f"{HELIS_DIR}/HZHC*.md")):
        data = parse_frontmatter(f)
        if data.get('registration'):
            heli = {
                'reg': data.get('registration', ''),
                'loc': data.get('location', 'RUH'),
                'status': 'parked',
                'note': '',
                'mission': data.get('current_mission', data.get('mission', ''))
            }
            
            status_raw = data.get('status', '').lower()
            if 'maintenance' in status_raw or 'unserviceable' in status_raw:
                heli['status'] = 'maint'
                # Extract note after " - "
                if ' - ' in data.get('status', ''):
                    heli['note'] = data.get('status', '').split(' - ', 1)[1]
            elif 'flying' in status_raw:
                heli['status'] = 'flying'
            
            # Check for note in status field
            if not heli['note'] and ' - ' in data.get('status', ''):
                heli['note'] = data.get('status', '').split(' - ', 1)[1]
            
            helicopters.append(heli)
    
    print(f"✅ Loaded {len(helicopters)} helicopters")
    return helicopters

def get_flights():
    """Parse flight schedule from Obsidian."""
    flights = {'today': [], 'sections': [], 'report_period': ''}
    today_flying = {}  # reg -> pilot
    
    if not os.path.exists(FLIGHTS_FILE):
        print("⚠️  No Flights Schedule.md found")
        return flights, today_flying
    
    with open(FLIGHTS_FILE, 'r') as f:
        content = f.read()
    
    # Get report period
    match = re.search(r'^report_period:\s*(.+)$', content, re.MULTILINE)
    if match:
        flights['report_period'] = match.group(1).strip()
    
    current_section = None
    section_flights = []
    
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('---') or line.startswith('report_period'):
            continue
        
        # Section header
        if line.startswith('## '):
            if current_section and section_flights:
                flights['sections'].append({'title': current_section, 'flights': section_flights})
            current_section = line[3:].strip()
            section_flights = []
            continue
        
        # Flight entry
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 4:
                reg = parts[1] if len(parts) > 1 else ''
                mission = parts[2] if len(parts) > 2 else ''
                pilot = parts[3] if len(parts) > 3 else ''
                flags = parts[4].lower() if len(parts) > 4 else ''
                
                is_today = 'today' in flags
                
                flight = {
                    'reg': reg,
                    'mission': mission,
                    'pilot': pilot,
                    'today': is_today
                }
                section_flights.append(flight)
                
                if is_today and pilot and pilot != 'TBA':
                    # Handle multi-helicopter entries like HC54/58/62
                    for r in reg.replace('HC', 'HZHC').split('/'):
                        r_clean = r.strip()
                        if not r_clean.startswith('HZHC'):
                            r_clean = 'HZHC' + r_clean
                        today_flying[r_clean] = pilot
    
    if current_section and section_flights:
        flights['sections'].append({'title': current_section, 'flights': section_flights})
    
    print(f"✅ Loaded flight schedule ({len(today_flying)} flying today)")
    return flights, today_flying

def get_pilot_currency():
    """Get pilot currency status from Obsidian."""
    currency = {
        'comp_this': [], 'comp_next': [], 'comp_overdue': [],
        'rems_this': [], 'rems_next': [], 'rems_overdue': [],
        'med_this': [], 'med_next': [], 'med_overdue': []
    }
    
    for pilot_dir in glob.glob(f"{PILOTS_DIR}/*/"):
        name = os.path.basename(pilot_dir.rstrip('/'))
        md_file = f"{pilot_dir}{name}.md"
        
        if not os.path.exists(md_file):
            continue
        
        data = parse_frontmatter(md_file)
        
        # Competency check (annual)
        comp = data.get('Last Competency Check', '')
        if comp and comp != 'N/A':
            try:
                comp_date = datetime.strptime(comp[:10], '%Y-%m-%d')
                due_date = comp_date.replace(year=comp_date.year + 1)
                due_ym = due_date.strftime('%Y-%m')
                
                if due_ym < TODAY_YM:
                    currency['comp_overdue'].append(name)
                elif due_ym == TODAY_YM:
                    currency['comp_this'].append(name)
                elif due_ym == NEXT_MONTH:
                    currency['comp_next'].append(name)
            except:
                pass
        
        # REMS (6 months from last flew)
        rems = data.get('30 Mins REMS', '')
        if rems and rems not in ['NA', 'N/A', '']:
            try:
                rems_ym = rems[:7]
                rems_date = datetime.strptime(f"{rems_ym}-01", '%Y-%m-%d')
                expiry_date = rems_date + timedelta(days=180)
                expiry_ym = expiry_date.strftime('%Y-%m')
                
                if expiry_ym < TODAY_YM:
                    currency['rems_overdue'].append(f"{name} — last flew {rems_date.strftime('%B %Y')}")
                elif expiry_ym == TODAY_YM:
                    currency['rems_this'].append(f"{name} — last flew {rems_date.strftime('%B %Y')}")
                elif expiry_ym == NEXT_MONTH:
                    currency['rems_next'].append(f"{name} — last flew {rems_date.strftime('%B %Y')}")
            except:
                pass
        
        # Medical (12 months)
        med = data.get('Medical Certificate Date', '')
        if med and med not in ['NA', 'N/A', '']:
            try:
                med_date = datetime.strptime(med[:10], '%Y-%m-%d')
                expiry_date = med_date.replace(year=med_date.year + 1)
                expiry_ym = expiry_date.strftime('%Y-%m')
                
                if expiry_ym < TODAY_YM:
                    currency['med_overdue'].append(f"{name} — issued {med_date.strftime('%B %Y')}")
                elif expiry_ym == TODAY_YM:
                    currency['med_this'].append(f"{name} — issued {med_date.strftime('%B %Y')}")
                elif expiry_ym == NEXT_MONTH:
                    currency['med_next'].append(f"{name} — issued {med_date.strftime('%B %Y')}")
            except:
                pass
    
    print(f"✅ Loaded pilot currency data")
    return currency

def get_missions():
    """Get mission data for timeline."""
    missions = []
    
    for f in glob.glob(f"{MISSIONS_DIR}/**/*.md", recursive=True):
        data = parse_frontmatter(f)
        if data.get('title') and data.get('date'):
            mission = {
                'title': data.get('title', ''),
                'status': data.get('status', 'pending'),
                'date': data.get('date', ''),
                'endDate': data.get('endDate', data.get('date', '')),
                'helicopters': data.get('Helicopter', ''),
                'pilots': data.get('Pilots', '')
            }
            missions.append(mission)
    
    # Sort by date
    missions.sort(key=lambda x: x['date'])
    print(f"✅ Loaded {len(missions)} missions for timeline")
    return missions

def build_fleet_js(helicopters, today_flying):
    """Build the JavaScript fleet array."""
    lines = ["const fleet = ["]
    
    counts = {'parked': 0, 'flying': 0, 'maint': 0}
    
    for h in helicopters:
        reg = h['reg']
        status = h['status']
        pilot = ''
        
        # Check if flying today
        if reg in today_flying:
            status = 'flying'
            pilot = today_flying[reg]
        
        counts[status] = counts.get(status, 0) + 1
        
        entry = f'  {{ reg: "{reg}", loc: "{h["loc"]}", status: "{status}"'
        if h['note']:
            entry += f', note: "{h["note"]}"'
        if h['mission']:
            entry += f', mission: "{h["mission"]}"'
        if pilot:
            entry += f', pilot: "{pilot}"'
        entry += ' },'
        lines.append(entry)
    
    lines.append("];")
    
    print(f"✅ Fleet: {counts['parked']} serviceable, {counts['flying']} flying, {counts['maint']} maintenance")
    return '\n'.join(lines), counts

def build_flights_html(flights):
    """Build the flights schedule HTML."""
    lines = []
    
    for section in flights['sections']:
        lines.append(f'  <h4>{section["title"]}</h4>')
        for f in section['flights']:
            today_class = ' today' if f['today'] else ''
            lines.append(f'  <div class="flight-row{today_class}">'
                        f'<span class="reg">{f["reg"]}</span>'
                        f'<span class="info">{f["mission"]}</span>'
                        f'<span class="pilot">{f["pilot"]}</span></div>')
    
    return '\n'.join(lines)

def build_currency_html(currency):
    """Build the pilot currency HTML."""
    lines = []
    
    # Competency
    lines.append('  <h4>Competency Checks</h4>')
    if currency['comp_this']:
        names = ', '.join(currency['comp_this'])
        lines.append(f'  <div class="alert warn">⚠️ {THIS_MONTH_NAME} — {names}</div>')
    else:
        lines.append(f'  <div class="alert ok">✅ {THIS_MONTH_NAME} — nobody due</div>')
    
    if currency['comp_next']:
        names = ', '.join(currency['comp_next'])
        lines.append(f'  <div class="alert warn">⚠️ {NEXT_MONTH_NAME} — {names}</div>')
    else:
        lines.append(f'  <div class="alert ok">✅ {NEXT_MONTH_NAME} — nobody due</div>')
    
    if currency['comp_overdue']:
        names = ', '.join(currency['comp_overdue'])
        lines.append(f'  <div class="alert danger">🔴 Overdue: {names}</div>')
    
    # REMS
    lines.append('  <h4>30-Min REMS (6 month cycle)</h4>')
    if currency['rems_this']:
        for item in currency['rems_this']:
            lines.append(f'  <div class="alert warn">⚠️ Due now: {item}</div>')
    if currency['rems_next']:
        for item in currency['rems_next']:
            lines.append(f'  <div class="alert warn">⚠️ Due next month: {item}</div>')
    if currency['rems_overdue']:
        for item in currency['rems_overdue']:
            lines.append(f'  <div class="alert danger">🔴 Overdue: {item}</div>')
    if not currency['rems_this'] and not currency['rems_next'] and not currency['rems_overdue']:
        lines.append('  <div class="alert ok">✅ All REMS current</div>')
    
    # Medical
    lines.append('  <h4>Medical Certificate (12 month validity)</h4>')
    if currency['med_this']:
        for item in currency['med_this']:
            lines.append(f'  <div class="alert warn">⚠️ Expires this month: {item}</div>')
    if currency['med_next']:
        for item in currency['med_next']:
            lines.append(f'  <div class="alert warn">⚠️ Expires next month: {item}</div>')
    if currency['med_overdue']:
        for item in currency['med_overdue']:
            lines.append(f'  <div class="alert danger">🔴 Expired: {item}</div>')
    if not currency['med_this'] and not currency['med_next'] and not currency['med_overdue']:
        lines.append('  <div class="alert ok">✅ All medicals current</div>')
    
    return '\n'.join(lines)

def build_timeline_html(missions):
    """Build the fancy missions timeline HTML with lanes and event bars."""
    from datetime import datetime, timedelta
    
    # Separate TBD missions from dated missions
    tbd_missions = [m for m in missions if not m.get('date')]
    dated_missions = [m for m in missions if m.get('date')]
    
    if not dated_missions:
        return "<!-- No dated missions -->"
    
    # Parse dates and find range
    def parse_date(d):
        try:
            return datetime.strptime(str(d), "%Y-%m-%d")
        except:
            return None
    
    for m in dated_missions:
        m['start_dt'] = parse_date(m['date'])
        m['end_dt'] = parse_date(m['endDate']) or m['start_dt']
    
    dated_missions = [m for m in dated_missions if m['start_dt']]
    dated_missions.sort(key=lambda x: x['start_dt'])
    
    # Timeline range: 1 month before earliest to 1 month after latest
    min_date = min(m['start_dt'] for m in dated_missions) - timedelta(days=30)
    max_date = max(m['end_dt'] for m in dated_missions) + timedelta(days=30)
    total_days = (max_date - min_date).days
    
    def calc_position(start, end):
        left = ((start - min_date).days / total_days) * 100
        width = max(((end - start).days / total_days) * 100, 1.2)
        return left, width
    
    def format_dates(start, end):
        if start == end:
            return start.strftime("%-d %b")
        elif start.month == end.month and start.year == end.year:
            return f"{start.strftime('%-d')}-{end.strftime('%-d %b')}"
        else:
            return f"{start.strftime('%-d %b')} - {end.strftime('%-d %b')}"
    
    # Assign lanes (alternate above/below)
    lanes_above = []
    lanes_below = []
    for i, m in enumerate(dated_missions):
        if i % 2 == 0:
            lanes_above.append(m)
        else:
            lanes_below.append(m)
    
    # Build TBD sidebar
    tbd_html = ""
    if tbd_missions:
        tbd_items = ""
        for m in tbd_missions:
            title = m['title'] if isinstance(m['title'], str) else (m['title'][0] if m['title'] else 'Unknown')
            tbd_items += f'''      <div class="tbd-item" data-name="{title}" data-status="pending" 
           data-dates="TBD" data-aircraft="TBD" 
           data-pilots="TBD" onclick="showEventPopup(this, event)">
        {title}
      </div>
'''
        tbd_html = f'''    <div class="tbd-sidebar">
      <div class="tbd-header">📋 Dates TBD</div>
{tbd_items}    </div>'''
    
    # Build event bars
    def build_bar(m):
        left, width = calc_position(m['start_dt'], m['end_dt'])
        status = m['status']
        title = m['title'] if isinstance(m['title'], str) else (m['title'][0] if m['title'] else 'Unknown')
        dates_str = format_dates(m['start_dt'], m['end_dt'])
        short = "short" if width < 5 else ""
        display_title = (title[:10] + "…") if len(title) > 10 and short else title
        helicopter = m.get('helicopters', 'TBD') or 'TBD'
        pilots = m.get('pilots', 'TBD') or 'TBD'
        
        return f'''          <div class="event-bar {status} {short}" style="left: {left:.2f}%; width: {width:.2f}%;"
               data-name="{title}" data-status="{status}" 
               data-dates="{dates_str}" data-aircraft="{helicopter}" 
               data-pilots="{pilots}" onclick="showEventPopup(this, event)"
               title="{title} ({dates_str})">
            <span class="event-title">{display_title}</span>
            <span class="event-dates">{dates_str}</span>
            <div class="connector"></div>
          </div>'''
    
    above_html = ""
    for m in lanes_above:
        above_html += f'''        <div class="lane">
{build_bar(m)}
        </div>
'''
    
    below_html = ""
    for m in lanes_below:
        below_html += f'''        <div class="lane">
{build_bar(m)}
        </div>
'''
    
    # Build month markers
    months_html = ""
    current = min_date.replace(day=1)
    while current <= max_date:
        left = ((current - min_date).days / total_days) * 100
        months_html += f'''        <div class="month-marker" style="left: {left:.2f}%;">{current.strftime("%b %Y")}</div>
'''
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    # Today marker
    today = datetime.now()
    today_marker = ""
    if min_date <= today <= max_date:
        today_left = ((today - min_date).days / total_days) * 100
        today_marker = f'''      <div class="today-marker" style="left: {today_left:.2f}%;"><span>Today</span></div>'''
    
    return f'''    <div class="timeline-wrapper">
{tbd_html}
    <div class="timeline-body">
      <div class="lanes-above">
{above_html}      </div>
      <div class="timeline-axis">
        <div class="axis-line"></div>
{months_html}{today_marker}
      </div>
      <div class="lanes-below">
{below_html}      </div>
    </div>
    </div>'''


def update_html(html_content, fleet_js, flights_html, currency_html, timeline_html, report_period):
    """Update the HTML file with new content."""
    
    # Update fleet array
    html_content = re.sub(
        r'// FLEET_START\n.*?// FLEET_END',
        f'// FLEET_START\n{fleet_js}\n// FLEET_END',
        html_content,
        flags=re.DOTALL
    )
    
    # Update flights
    html_content = re.sub(
        r'<!-- FLIGHTS_START -->\n.*?<!-- FLIGHTS_END -->',
        f'<!-- FLIGHTS_START -->\n{flights_html}\n  <!-- FLIGHTS_END -->',
        html_content,
        flags=re.DOTALL
    )
    
    # Update currency
    html_content = re.sub(
        r'<!-- CURRENCY_START -->\n.*?<!-- CURRENCY_END -->',
        f'<!-- CURRENCY_START -->\n{currency_html}\n  <!-- CURRENCY_END -->',
        html_content,
        flags=re.DOTALL
    )
    
    # Update timeline
    html_content = re.sub(
        r'<!-- TIMELINE_START -->\n.*?<!-- TIMELINE_END -->',
        f'<!-- TIMELINE_START -->\n{timeline_html}\n    <!-- TIMELINE_END -->',
        html_content,
        flags=re.DOTALL
    )
    
    # Update dates
    timestamp = TODAY.strftime("%-d %b %Y %H:%M")
    html_content = re.sub(
        r'<!-- LAST_UPDATED -->.*?<!-- /LAST_UPDATED -->',
        f'<!-- LAST_UPDATED -->{timestamp}<!-- /LAST_UPDATED -->',
        html_content
    )
    
    html_content = re.sub(
        r'<!-- LEGEND_DATE -->.*?<!-- /LEGEND_DATE -->',
        f'<!-- LEGEND_DATE -->{TODAY_DISPLAY}<!-- /LEGEND_DATE -->',
        html_content
    )
    
    html_content = re.sub(
        r'<!-- REPORT_PERIOD -->.*?<!-- /REPORT_PERIOD -->',
        f'<!-- REPORT_PERIOD -->{report_period}<!-- /REPORT_PERIOD -->',
        html_content
    )
    
    html_content = re.sub(
        r'<title>.*?</title>',
        f'<title>THC Fleet Map — {TODAY_DISPLAY}</title>',
        html_content
    )
    
    return html_content

def main():
    print(f"\n🚁 THC Fleet Map Generator (Python)")
    print(f"   {TODAY.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Load data
    helicopters = get_helicopters()
    flights, today_flying = get_flights()
    currency = get_pilot_currency()
    missions = get_missions()
    
    # Build content
    fleet_js, counts = build_fleet_js(helicopters, today_flying)
    flights_html = build_flights_html(flights)
    currency_html = build_currency_html(currency)
    timeline_html = build_timeline_html(missions)
    
    # Read HTML
    with open(HTML_FILE, "r") as f:
        html_content = f.read()
    
    # Update HTML
    html_content = update_html(
        html_content, 
        fleet_js, 
        flights_html, 
        currency_html, 
        timeline_html,
        flights['report_period']
    )
    
    # Write HTML
    with open(HTML_FILE, 'w') as f:
        f.write(html_content)
    
    print(f"\n✅ Updated {HTML_FILE}")
    print(f"✅ Page title: THC Fleet Map — {TODAY_DISPLAY}")
    print(f"\nDone! Review: open {HTML_FILE}")
    print(f"Live site: https://willslawrence.github.io/thc-ops-map/\n")

if __name__ == "__main__":
    main()
