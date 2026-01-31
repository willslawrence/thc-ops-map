#!/usr/bin/env python3
"""generate_sandbox.py - Regenerates THC Fleet Map from Obsidian vault."""

import os, re, glob
from datetime import datetime, timedelta

VAULT = "/thc-vault"
HELIS_DIR = f"{VAULT}/Helicopters"
PILOTS_DIR = f"{VAULT}/Pilots"
FLIGHTS_FILE = f"{VAULT}/Flights Schedule.md"
MISSIONS_DIR = f"{VAULT}/Missions"
HTML_FILE = "/willy/FleetMapAndTimeline/index.html"
TODAY = datetime.now()

def parse_frontmatter(filepath):
    data = {}
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                current_key = None
                current_list = []
                for line in parts[1].strip().split('\n'):
                    if line.strip().startswith('- '):
                        if current_key:
                            current_list.append(line.strip()[2:].strip())
                    elif ':' in line:
                        if current_key and current_list:
                            data[current_key] = current_list[0] if len(current_list) == 1 else ', '.join(current_list)
                            current_list = []
                        key, val = line.split(':', 1)
                        current_key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if val:
                            data[current_key] = val
                            current_key = None
                if current_key and current_list:
                    data[current_key] = current_list[0] if len(current_list) == 1 else ', '.join(current_list)
    except Exception as e:
        print(f"  Warning: {filepath}: {e}")
    return data

def load_helicopters():
    helicopters = []
    for f in sorted(glob.glob(f"{HELIS_DIR}/HZHC*.md")):
        data = parse_frontmatter(f)
        helicopters.append({
            'reg': data.get('registration', os.path.basename(f).replace('.md', '')),
            'loc': data.get('location', 'UNK'),
            'status': data.get('status', 'parked'),
            'mission': data.get('mission', ''),
            'note': data.get('note', '')
        })
    print(f"✅ Loaded {len(helicopters)} helicopters")
    return helicopters

def load_flights():
    flights, today_flying = [], {}
    try:
        with open(FLIGHTS_FILE, 'r') as f:
            content = f.read()
        today_str = TODAY.strftime("%Y-%m-%d")
        in_today = False
        for line in content.split('\n'):
            if today_str in line:
                in_today = True
            elif in_today:
                if line.startswith('## ') or line.startswith('# '):
                    break
                if '|' in line and 'HC' in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 4:
                        reg = 'HZHC' + parts[1].replace('HC', '') if 'HC' in parts[1] else parts[1]
                        flights.append({'reg': reg, 'mission': parts[2], 'pilot': parts[3]})
                        today_flying[reg] = parts[3]
    except Exception as e:
        print(f"  Warning: {e}")
    print(f"✅ Loaded {len(flights)} flights for today")
    return flights, today_flying

def load_currency():
    currency = []
    for pilot_dir in glob.glob(f"{PILOTS_DIR}/*/"):
        name = os.path.basename(pilot_dir.rstrip('/'))
        cfile = os.path.join(pilot_dir, "Currency.md")
        if os.path.exists(cfile):
            data = parse_frontmatter(cfile)
            currency.append({'name': name, 'medical': data.get('medical', ''), 'rems': data.get('rems', '')})
    print(f"✅ Loaded {len(currency)} pilot currency records")
    return currency

def load_missions():
    missions = []
    for pattern in [f"{MISSIONS_DIR}/*.md", f"{MISSIONS_DIR}/Past Missions/*.md"]:
        for f in glob.glob(pattern):
            data = parse_frontmatter(f)
            title = data.get('title', os.path.basename(f).replace('.md', ''))
            missions.append({
                'title': title, 'date': data.get('date', ''), 'endDate': data.get('endDate', data.get('date', '')),
                'status': data.get('status', 'pending'), 'helicopters': data.get('Helicopter', ''), 'pilots': data.get('Pilots', '')
            })
    missions.sort(key=lambda x: x['date'] if x['date'] else 'zzzz')
    print(f"✅ Loaded {len(missions)} missions")
    return missions

def build_fleet_js(helicopters, today_flying):
    lines = ["const fleet = ["]
    counts = {'parked': 0, 'flying': 0, 'maint': 0}
    for h in helicopters:
        reg, status, pilot = h['reg'], h['status'], today_flying.get(h['reg'], '')
        if h['reg'] in today_flying:
            status = 'flying'
        counts[status] = counts.get(status, 0) + 1
        entry = f'  {{ reg: "{reg}", loc: "{h["loc"]}", status: "{status}"'
        if h['note']: entry += f', note: "{h["note"]}"'
        if h['mission']: entry += f', mission: "{h["mission"]}"'
        if pilot: entry += f', pilot: "{pilot}"'
        lines.append(entry + ' },')
    lines.append("];")
    print(f"✅ Fleet: {counts.get('parked',0)} serviceable, {counts.get('flying',0)} flying, {counts.get('maint',0)} maintenance")
    return '\n'.join(lines)

def build_flights_html(flights):
    if not flights: return '<div class="no-flights">No flights today</div>'
    return '\n'.join([f'  <div class="flight-row today"><span class="reg">{f["reg"].replace("HZHC","HC")}</span><span class="info">{f["mission"]}</span><span class="pilot">{f["pilot"]}</span></div>' for f in flights])

def build_currency_html(currency):
    return '\n'.join([f'  <div class="currency-row"><span class="pilot-name">{c["name"]}</span><span class="medical">{c["medical"]}</span><span class="rems">{c["rems"]}</span></div>' for c in currency])

def build_timeline_html(missions):
    tbd = [m for m in missions if not m['date']]
    dated = [m for m in missions if m['date']]
    if not dated: return "<!-- No dated missions -->"
    
    def parse_dt(d):
        try: return datetime.strptime(d, "%Y-%m-%d")
        except: return None
    
    for m in dated:
        m['start_dt'] = parse_dt(m['date'])
        m['end_dt'] = parse_dt(m['endDate']) or m['start_dt']
    dated = [m for m in dated if m['start_dt']]
    dated.sort(key=lambda x: x['start_dt'])
    
    min_date, max_date = datetime(2025, 10, 1), datetime(2026, 12, 31)
    total_days = (max_date - min_date).days
    
    def calc_pos(s, e):
        left = ((max(s, min_date) - min_date).days / total_days) * 100
        width = max(((min(e, max_date) - max(s, min_date)).days / total_days) * 100, 1.2)
        return round(left, 1), round(width, 1)
    
    def fmt_dt(s, e):
        if s == e: return s.strftime("%-d %b")
        elif s.month == e.month: return f"{s.day}-{e.strftime('%-d %b')}"
        else: return f"{s.strftime('%-d %b')} - {e.strftime('%-d %b')}"
    
    def overlaps(a, b):
        buf = timedelta(days=2)
        return not (a['end_dt'] + buf < b['start_dt'] or b['end_dt'] + buf < a['start_dt'])
    
    def pack(events):
        lanes = []
        for ev in events:
            placed = False
            for lane in lanes:
                if not any(overlaps(ev, e) for e in lane): lane.append(ev); placed = True; break
            if not placed: lanes.append([ev])
        return lanes
    
    all_lanes = pack(dated)
    lanes_above, lanes_below = all_lanes[::2], all_lanes[1::2]
    
    L = ['    <div class="timeline-wrapper">']
    if tbd:
        L.append('    <div class="tbd-sidebar">')
        L.append('      <div class="tbd-header">📋 Dates TBD</div>')
        for m in tbd:
            t = m['title']
            L.append(f'      <div class="tbd-item" data-name="{t}" data-status="pending" data-dates="TBD" data-aircraft="TBD" data-pilots="TBD" onclick="showEventPopup(this, event)">')
            L.append(f'        {t}')
            L.append('      </div>')
        L.append('    </div>')
    
    def bar(m):
        left, width = calc_pos(m['start_dt'], m['end_dt'])
        t, st, dt = m['title'], m['status'], fmt_dt(m['start_dt'], m['end_dt'])
        sh = "short" if width < 8 else ""
        disp = (t[:10] + "...") if len(t) > 12 and sh else t
        h, p = m.get('helicopters') or 'TBD', m.get('pilots') or 'TBD'
        b = [f'          <div class="event-bar {st} {sh}" style="left: {left}%; width: {width}%;" data-name="{t}" data-status="{st}" data-dates="{dt}" data-aircraft="{h}" data-pilots="{p}" onclick="showEventPopup(this, event)" title="{t} ({dt})">']
        b.append(f'            <span class="event-title">{disp}</span>')
        if not sh: b.append(f'            <span class="event-dates">{dt}</span>')
        b.append('          </div>')
        return '\n'.join(b)
    
    L.append('    <div class="timeline-body">')
    L.append('      <div class="lanes-above">')
    for lane in lanes_above:
        L.append('        <div class="lane">')
        for m in sorted(lane, key=lambda x: x['start_dt']): L.append(bar(m))
        L.append('        </div>')
    L.append('      </div>')
    
    L.append('      <div class="timeline-axis">')
    L.append('        <div class="axis-line"></div>')
    curr = min_date
    while curr <= max_date:
        left = round(((curr - min_date).days / total_days) * 100, 1)
        L.append(f'        <div class="month-marker" style="left: {left}%;">{curr.strftime("%b %Y")}</div>')
        curr = (curr.replace(day=1) + timedelta(days=32)).replace(day=1)
    if min_date <= TODAY <= max_date:
        L.append(f'      <div class="today-marker" style="left: {round(((TODAY - min_date).days / total_days) * 100, 1)}%;"><span>Today</span></div>')
    L.append('      </div>')
    
    L.append('      <div class="lanes-below">')
    for lane in lanes_below:
        L.append('        <div class="lane">')
        for m in sorted(lane, key=lambda x: x['start_dt']): L.append(bar(m))
        L.append('        </div>')
    L.append('      </div>')
    L.append('    </div>')
    L.append('    </div>')
    return '\n'.join(L)

def update_html(content, fleet_js, flights_html, currency_html, timeline_html):
    content = re.sub(r'const fleet = \[.*?\];', fleet_js, content, flags=re.DOTALL)
    content = re.sub(r'<!-- FLIGHTS_START -->.*?<!-- FLIGHTS_END -->', f'<!-- FLIGHTS_START -->\n{flights_html}\n  <!-- FLIGHTS_END -->', content, flags=re.DOTALL)
    content = re.sub(r'<!-- CURRENCY_START -->.*?<!-- CURRENCY_END -->', f'<!-- CURRENCY_START -->\n{currency_html}\n  <!-- CURRENCY_END -->', content, flags=re.DOTALL)
    content = re.sub(r'<!-- TIMELINE_START -->.*?<!-- TIMELINE_END -->', f'<!-- TIMELINE_START -->\n{timeline_html}\n    <!-- TIMELINE_END -->', content, flags=re.DOTALL)
    content = re.sub(r'<title>THC Fleet Map.*?</title>', f'<title>THC Fleet Map — {TODAY.strftime("%-d %b %Y")}</title>', content)
    return content

def main():
    print(f"\n🚁 THC Fleet Map Generator\n   {TODAY.strftime('%Y-%m-%d %H:%M:%S')}\n")
    helicopters = load_helicopters()
    flights, today_flying = load_flights()
    currency = load_currency()
    missions = load_missions()
    fleet_js = build_fleet_js(helicopters, today_flying)
    flights_html = build_flights_html(flights)
    currency_html = build_currency_html(currency)
    timeline_html = build_timeline_html(missions)
    with open(HTML_FILE, 'r') as f: html = f.read()
    html = update_html(html, fleet_js, flights_html, currency_html, timeline_html)
    with open(HTML_FILE, 'w') as f: f.write(html)
    print(f"\n✅ Updated {HTML_FILE}")
    print(f"✅ Title: THC Fleet Map — {TODAY.strftime('%-d %b %Y')}")
    print(f"\nDone! open {HTML_FILE}")

if __name__ == "__main__": main()
