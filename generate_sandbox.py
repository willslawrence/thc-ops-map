#!/usr/bin/env python3
import os, re, glob
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VAULT = "/thc-vault"
HELIS_DIR = f"{VAULT}/Helicopters"
PILOTS_DIR = f"{VAULT}/Pilots"
FLIGHTS_FILE = f"{VAULT}/Flights Schedule.md"
MISSIONS_DIR = f"{VAULT}/Missions"
HTML_FILE = "/willy/FleetMapAndTimeline/index.html"
# Use Saudi Arabia timezone, then strip tz for naive comparisons
_now = datetime.now(ZoneInfo("Asia/Riyadh"))
TODAY = datetime(_now.year, _now.month, _now.day, _now.hour, _now.minute, _now.second)

def parse_fm(fp):
    d = {}
    try:
        t = open(fp).read()
        if t.startswith('---'):
            p = t.split('---', 2)
            if len(p) >= 3:
                k, lst = None, []
                nested_key = None
                nested_dict = {}
                for ln in p[1].strip().split('\n'):
                    stripped = ln.strip()
                    indent = len(ln) - len(ln.lstrip())
                    if indent >= 2 and nested_key:
                        # Inside a nested block
                        if stripped.startswith('- '):
                            lst.append(stripped[2:].strip())
                        elif ':' in stripped:
                            nk, nv = stripped.split(':', 1)
                            nv = nv.strip().strip('"').strip("'")
                            if nv:
                                nested_dict[nk.strip()] = nv
                        continue
                    # Top-level line - flush previous
                    if nested_key and nested_dict:
                        d[nested_key] = nested_dict
                        nested_dict = {}
                        nested_key = None
                    if k and lst:
                        d[k] = lst[0] if len(lst)==1 else ', '.join(lst)
                        lst = []
                        k = None
                    if stripped.startswith('- '):
                        if k: lst.append(stripped[2:].strip())
                    elif ':' in stripped:
                        kk, v = stripped.split(':', 1)
                        kk = kk.strip()
                        v = v.strip().strip('"').strip("'")
                        if v:
                            d[kk] = v
                            k = None
                        else:
                            # Could be start of nested block or list
                            nested_key = kk
                            nested_dict = {}
                            k = kk
                            lst = []
                # Flush final
                if nested_key and nested_dict:
                    d[nested_key] = nested_dict
                elif k and lst:
                    d[k] = lst[0] if len(lst)==1 else ', '.join(lst)
    except: pass
    return d

def load_helis():
    h = []
    for f in sorted(glob.glob(f"{HELIS_DIR}/HZHC*.md")):
        d = parse_fm(f)
        st = d.get('status', 'parked').lower()
        if 'serviceable' in st: st = 'parked'
        elif 'maint' in st or 'aog' in st: st = 'maint'
        else: st = 'parked'
        h.append({
            'reg': d.get('registration', os.path.basename(f).replace('.md','')),
            'loc': d.get('location','UNK'),
            'status': st,
            'mission': d.get('current_mission',''),
            'note': d.get('notes', d.get('note','')),
            'ert': d.get('ert',''),
            'total_fh': d.get('total_fh',''),
            '150hr_rem_fh': d.get('150hr_rem_fh',''),
            '12mo_due': d.get('12mo_due',''),
        })
    print(f"✅ Loaded {len(h)} helicopters")
    return h

def is_h125(reg_field):
    """Check if registration is in HC50-HC70 range (H125 only)"""
    # Extract number from reg like HC55, HZHC55, etc.
    m = re.search(r'HC(\d+)', reg_field)
    if m:
        num = int(m.group(1))
        return 50 <= num <= 70
    return False

def load_flights():
    fl, fy, fr = [], {}, {}  # fr = flight routes
    try:
        t = open(FLIGHTS_FILE).read()
        ts = TODAY.strftime("%Y-%m-%d")
        for ln in t.split('\n'):
            if ln.startswith(ts) and '|' in ln:
                p = [x.strip() for x in ln.split('|')]
                if len(p) >= 4:
                    if not is_h125(p[1]):
                        continue  # Skip non-H125 aircraft
                    r = 'HZHC' + p[1].replace('HC','') if not p[1].startswith('HZ') else p[1]
                    mission = p[2]
                    fl.append({'reg': r, 'mission': mission, 'pilot': p[3]})
                    fy[r] = p[3]
                    # Parse route for repositions (dest is 4-letter ICAO code)
                    if 'reposition' in mission.lower() and ' - ' in mission:
                        dest = mission.split(' - ')[-1].strip()
                        if len(dest) == 4 and dest.isupper():  # ICAO code
                            fr[r] = {'mission': mission, 'dest': dest}
    except: pass
    print(f"✅ Loaded {len(fl)} flights")
    return fl, fy, fr

def load_currency():
    c = []
    for pd in glob.glob(f"{PILOTS_DIR}/*/"):
        nm = os.path.basename(pd.rstrip('/'))
        pf = os.path.join(pd, f"{nm}.md")
        if os.path.exists(pf):
            try:
                t = open(pf).read()
                med = rems = comp = ""
                for ln in t.split('\n'):
                    if 'Medical Certificate Date:' in ln: med = ln.split(':',1)[1].strip()
                    if '30 Mins REMS:' in ln: rems = ln.split(':',1)[1].strip()
                    if 'Last Competency Check:' in ln: comp = ln.split(':',1)[1].strip()
                c.append({'name': nm, 'medical': med, 'rems': rems, 'competency': comp})
            except: pass
    print(f"✅ Loaded {len(c)} currency records")
    return c

def load_missions():
    m = []
    for pat in [f"{MISSIONS_DIR}/*.md", f"{MISSIONS_DIR}/Past Missions/*.md"]:
        for f in glob.glob(pat):
            d = parse_fm(f)
            t = d.get('title', os.path.basename(f).replace('.md',''))
            # Format helicopter roles
            helis = d.get('helicopters', d.get('Helicopter', ''))
            if isinstance(helis, dict):
                # New role-based format: {Film: HZHC55, EMS 1: HZHC57, ...}
                heli_str = ' | '.join(f"{role}: {reg.replace('HZHC','HC')}" for role, reg in helis.items())
            elif isinstance(helis, str):
                heli_str = helis.replace('HZHC','HC') if helis else 'TBD'
            else:
                heli_str = 'TBD'
            pilots = d.get('Pilots', '')
            # Auto-determine status from dates
            # past = ended before today (grey)
            # active = happening now (green)
            # pending = future, unconfirmed (red)
            # confirmed = future, confirmed (blue)
            raw_status = d.get('status','pending')
            start = d.get('date','')
            end = d.get('endDate', start)
            if raw_status in ('past', 'complete'):
                auto_status = raw_status
            elif start:
                ts = TODAY.strftime("%Y-%m-%d")
                if end and end < ts:
                    auto_status = 'past'
                elif start <= ts and (not end or end >= ts):
                    auto_status = 'active'
                else:
                    # Future mission — use frontmatter status
                    auto_status = raw_status if raw_status in ('confirmed', 'pending') else 'pending'
            else:
                auto_status = raw_status
            m.append({'title': t, 'date': start, 'endDate': end, 'status': auto_status, 'helicopters': heli_str, 'pilots': pilots})
    m.sort(key=lambda x: x['date'] if x['date'] else 'zzzz')
    print(f"✅ Loaded {len(m)} missions")
    return m

def build_fleet_js(helis, fy, fr):
    L = ["const fleet = ["]
    cnt = {'parked':0, 'flying':0, 'maint':0}
    for h in helis:
        st = 'flying' if h['reg'] in fy else h['status']
        cnt[st] = cnt.get(st,0) + 1
        e = f'  {{ reg: "{h["reg"]}", loc: "{h["loc"]}", status: "{st}"'
        if h['note']: e += f', note: "{h["note"]}"'
        if h['mission']: e += f', mission: "{h["mission"]}"'
        if h['ert']: e += f', ert: "{h["ert"]}"'
        if h['total_fh']: e += f', totalFH: "{h["total_fh"]}"'
        if h['150hr_rem_fh']: e += f', remFH: "{h["150hr_rem_fh"]}"'
        if h['12mo_due']: e += f', next12mo: "{h["12mo_due"]}"'
        if h['reg'] in fy: e += f', pilot: "{fy[h["reg"]]}"'
        # Add route info for flying helicopters
        if h['reg'] in fr:
            route = fr[h['reg']]
            e += f', route: "{h["loc"]} → {route["dest"]}"'
        L.append(e + ' },')
    L.append("];")
    print(f"✅ Fleet: {cnt['parked']} serviceable, {cnt['flying']} flying, {cnt['maint']} maint")
    return '\n'.join(L)

def build_flights_html():
    L = []
    ts = TODAY.strftime("%Y-%m-%d")
    current_section_is_past = False
    try:
        t = open(FLIGHTS_FILE).read()
        for ln in t.split('\n'):
            if ln.startswith('## '):
                # Check if this section header is for a past date
                # Parse date from section flights below, or check header text
                section_title = ln[3:].strip()
                current_section_is_past = False  # Reset, will determine from flight dates
                pending_header = f'  <h4>{section_title}</h4>'
                header_added = False
            elif '|' in ln and not ln.startswith('#'):
                p = [x.strip() for x in ln.split('|')]
                if len(p) >= 4:
                    # Skip past flights
                    flight_date = p[0]
                    if flight_date < ts:
                        continue
                    # Skip non-H125 aircraft
                    if not is_h125(p[1]):
                        continue
                    # Add section header if not yet added
                    if not header_added and pending_header:
                        L.append(pending_header)
                        header_added = True
                    r = p[1].replace('HZHC','HC') if 'HZ' in p[1] else p[1]
                    cl = "flight-row today" if p[0]==ts else "flight-row"
                    L.append(f'  <div class="{cl}"><span class="reg">{r}</span><span class="info">{p[2]}</span><span class="pilot">{p[3]}</span></div>')
    except: pass
    return '\n'.join(L) if L else '  <div>No flights scheduled</div>'

def build_currency_html(curr):
    L = []
    this_mo = TODAY.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_mo_end = (this_mo + timedelta(days=32)).replace(day=1)
    next_mo = this_mo_end
    next_mo_end = (next_mo + timedelta(days=32)).replace(day=1)
    
    # Competency - 12 months from last check
    comp_this = []
    comp_next = []
    for c in curr:
        cp = c.get('competency','')
        if cp:
            try:
                cd = datetime.strptime(cp, "%Y-%m-%d")
                exp = cd.replace(year=cd.year+1)
                first_name = c['name'].split()[0] + ' ' + c['name'].split()[-1][0] if len(c['name'].split()) > 1 else c['name'].split()[0]
                if this_mo <= exp < this_mo_end:
                    comp_this.append((first_name, exp.strftime("%b %Y")))
                elif next_mo <= exp < next_mo_end:
                    comp_next.append((first_name, exp.strftime("%b %Y")))
            except: pass
    L.append('  <h4>Competency Checks</h4>')
    if comp_this:
        for n, d in comp_this:
            L.append(f'  <div class="alert warn">⚠️ {n} - due {d}</div>')
    if comp_next:
        for n, d in comp_next:
            L.append(f'  <div class="alert info">📅 {n} - due {d}</div>')
    if not comp_this and not comp_next:
        L.append(f'  <div class="alert ok">✅ Nobody due this or next month</div>')
    
    # REMS 30 - 6 calendar months from last flight date
    # Flight in Aug = valid Aug,Sep,Oct,Nov,Dec,Jan = expires end of Jan (5 months after flight month)
    rems_issues = []
    for c in curr:
        r = c.get('rems','')
        if r:
            try:
                rd = datetime.strptime(r, "%Y-%m")
                # Expires 5 months after flight month (flight month + 5 more = 6 total)
                exp_month = rd.month + 5
                exp_year = rd.year + (exp_month - 1) // 12
                exp_month = ((exp_month - 1) % 12) + 1
                exp = datetime(exp_year, exp_month, 1)
                exp_end = (exp + timedelta(days=32)).replace(day=1)  # First of next month
                first_name = c['name'].split()[0] + ' ' + c['name'].split()[-1][0] if len(c['name'].split()) > 1 else c['name'].split()[0]
                if TODAY >= exp_end:
                    # Expired (we're past the expiry month)
                    rems_issues.append((first_name, exp.strftime("%b %Y"), 'danger', 'expired'))
                elif this_mo <= exp < this_mo_end:
                    # Expires this month
                    rems_issues.append((first_name, exp.strftime("%b %Y"), "warn", "expires"))
            except: pass
    if rems_issues:
        L.append('  <h4>30-Min REMS (6 month validity)</h4>')
        for n,d,lv,status in sorted(rems_issues, key=lambda x: x[2]!='danger'):
            L.append(f'  <div class="alert {lv}">{"🔴" if lv=="danger" else "⚠️"} {n} - {status} {d}</div>')
    
    # Medical - 12 months from check date
    med_issues = []
    this_month_start = TODAY.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_end = (this_month_start + timedelta(days=32)).replace(day=1)
    for c in curr:
        m = c.get('medical','')
        if m:
            try:
                md = datetime.strptime(m, "%Y-%m-%d")
                exp = md.replace(year=md.year+1)
                first_name = c['name'].split()[0] + ' ' + c['name'].split()[-1][0] if len(c['name'].split()) > 1 else c['name'].split()[0]
                if exp < this_month_start:
                    # Overdue
                    med_issues.append((first_name, exp.strftime("%b %Y"), 'danger', 'overdue since'))
                elif this_month_start <= exp < this_month_end:
                    # Due this month
                    med_issues.append((first_name, exp.strftime("%b %Y"), 'warn', 'due'))
                # Future months: don't show
            except: pass
    if med_issues:
        L.append('  <h4>Medical Certificate (12 month validity)</h4>')
        for n,d,lv,status in sorted(med_issues, key=lambda x: x[2]!='danger'):
            L.append(f'  <div class="alert {lv}">{"🔴" if lv=="danger" else "⚠️"} {n} - {status} {d}</div>')
    
    return '\n'.join(L)


def build_timeline(missions):
    tbd = [m for m in missions if not m['date']]
    dated = [m for m in missions if m['date']]
    if not dated: return "<!-- No missions -->"
    
    def pdt(d):
        try: return datetime.strptime(d, "%Y-%m-%d")
        except: return None
    
    for m in dated: m['s'], m['e'] = pdt(m['date']), pdt(m['endDate']) or pdt(m['date'])
    dated = [m for m in dated if m['s']]
    dated.sort(key=lambda x: x['s'])
    
    # Jan-Dec 2026 only
    mn, mx = datetime(2026,1,1), datetime(2026,12,31)
    td = (mx-mn).days
    
    # Filter to only missions that overlap with 2026
    dated = [m for m in dated if m['e'] >= mn and m['s'] <= mx]
    
    def pos(s,e): 
        s_clamped = max(s, mn)
        e_clamped = min(e, mx)
        return round(((s_clamped-mn).days/td)*100,1), max(round(((e_clamped-s_clamped).days/td)*100,1), 1.2)
    
    def fdt(s,e):
        if s==e: return s.strftime("%-d %b")
        elif s.month==e.month: return f"{s.day}-{e.strftime('%-d %b')}"
        return f"{s.strftime('%-d %b')} - {e.strftime('%-d %b')}"
    
    def ovl(a,b): return not (a['e']+timedelta(days=7) < b['s'] or b['e']+timedelta(days=7) < a['s'])
    
    # Pack into exactly 3 lanes above, 3 below (6 total)
    def pack_limited(evs, max_lanes=6):
        lanes = [[] for _ in range(max_lanes)]
        for ev in evs:
            placed = False
            for lane in lanes:
                if not any(ovl(ev,e) for e in lane): 
                    lane.append(ev)
                    placed = True
                    break
            if not placed:
                lanes[0].append(ev)
        return lanes
    
    lanes = pack_limited(dated, 6)
    # Alternate lanes: 0,2,4 above and 1,3,5 below for even distribution
    above = [lanes[i] for i in [0, 2, 4] if lanes[i]]
    below = [lanes[i] for i in [1, 3, 5] if lanes[i]]
    
    L = ['    <div class="timeline-wrapper">']
    if tbd:
        L.append('    <div class="tbd-sidebar">')
        L.append('      <div class="tbd-header">📋 Dates TBD</div>')
        for m in tbd: L.append(f'      <div class="tbd-item" data-name="{m["title"]}" data-status="pending" data-dates="TBD" data-aircraft="{m.get("helicopters","TBD")}" data-pilots="{m.get("pilots","TBD")}" onclick="showEventPopup(this,event)">\n        {m["title"]}\n      </div>')
        L.append('    </div>')
    
    def bar(m):
        l,w = pos(m['s'],m['e'])
        t,st,dt = m['title'], m['status'], fdt(m['s'],m['e'])
        sh = "short" if w<8 else ""
        dp = (t[:10]+"...") if len(t)>12 and sh else t
        h,p = m.get('helicopters') or 'TBD', m.get('pilots') or 'TBD'
        return f'          <div class="event-bar {st} {sh}" style="left:{l}%;width:{w}%;" data-name="{t}" data-status="{st}" data-dates="{dt}" data-aircraft="{h}" data-pilots="{p}" onclick="showEventPopup(this,event)" title="{t} ({dt})">\n            <span class="event-title">{dp}</span>' + (f'\n            <span class="event-dates">{dt}</span>' if not sh else '') + '\n          </div>'
    
    L.append('    <div class="timeline-body">')
    L.append('      <div class="lanes-above">')
    for lane in reversed(above):
        L.append('        <div class="lane">')
        for m in sorted(lane, key=lambda x: x['s']): L.append(bar(m))
        L.append('        </div>')
    L.append('      </div>')
    L.append('      <div class="timeline-axis">')
    L.append('        <div class="axis-line"></div>')
    
    # Month ticks (larger) with labels
    for month in range(1, 13):
        d = datetime(2026, month, 1)
        pct = round(((d-mn).days/td)*100,1)
        L.append(f'        <div class="month-tick" style="left:{pct}%;"><span class="tick-label">{d.strftime("%b")}</span></div>')
    
    # Week ticks (smaller) - every Monday
    c = mn
    while c <= mx:
        if c.weekday() == 0 and c.day != 1:
            pct = round(((c-mn).days/td)*100,1)
            L.append(f'        <div class="week-tick" style="left:{pct}%;"></div>')
        c += timedelta(days=1)
    
    if mn <= TODAY <= mx: 
        L.append(f'        <div class="today-marker" style="left:{round(((TODAY-mn).days/td)*100,1)}%;"></div>')
    
    L.append('      </div>')
    L.append('      <div class="lanes-below">')
    for lane in below:
        L.append('        <div class="lane">')
        for m in sorted(lane, key=lambda x: x['s']): L.append(bar(m))
        L.append('        </div>')
    L.append('      </div>')
    L.append('    </div>')
    L.append('    </div>')
    return '\n'.join(L)

def update(html, fleet, flights, curr, timeline):
    html = re.sub(r'const fleet = \[.*?\];', fleet, html, flags=re.DOTALL)
    html = re.sub(r'<!-- FLIGHTS_START -->.*?<!-- FLIGHTS_END -->', f'<!-- FLIGHTS_START -->\n{flights}\n  <!-- FLIGHTS_END -->', html, flags=re.DOTALL)
    html = re.sub(r'<!-- CURRENCY_START -->.*?<!-- CURRENCY_END -->', f'<!-- CURRENCY_START -->\n{curr}\n  <!-- CURRENCY_END -->', html, flags=re.DOTALL)
    html = re.sub(r'<!-- TIMELINE_START -->.*?<!-- TIMELINE_END -->', f'<!-- TIMELINE_START -->\n{timeline}\n    <!-- TIMELINE_END -->', html, flags=re.DOTALL)
    html = re.sub(r'<title>THC Fleet Map.*?</title>', f'<title>THC Fleet Map — {TODAY.strftime("%-d %b %Y")}</title>', html)
    html = re.sub(r'<!-- LAST_UPDATED -->.*?<!-- /LAST_UPDATED -->', f'<!-- LAST_UPDATED -->{TODAY.strftime("%-d %b %Y %H:%M")}<!-- /LAST_UPDATED -->', html)
    return html

def main():
    print(f"\n🚁 THC Fleet Map Generator\n   {TODAY.strftime('%Y-%m-%d %H:%M:%S')}\n")
    h = load_helis()
    fl, fy, fr = load_flights()
    c = load_currency()
    m = load_missions()
    html = open(HTML_FILE).read()
    html = update(html, build_fleet_js(h, fy, fr), build_flights_html(), build_currency_html(c), build_timeline(m))
    open(HTML_FILE, 'w').write(html)
    print(f"\n✅ Done!")

if __name__ == "__main__": main()
