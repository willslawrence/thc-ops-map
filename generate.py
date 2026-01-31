#!/usr/bin/env python3
import os, re, glob
from datetime import datetime, timedelta

VAULT = os.path.expanduser("~/Library/Mobile Documents/iCloud~md~obsidian/Documents/THC Vault")
HELIS_DIR = f"{VAULT}/Helicopters"
PILOTS_DIR = f"{VAULT}/Pilots"
FLIGHTS_FILE = f"{VAULT}/Flights Schedule.md"
MISSIONS_DIR = f"{VAULT}/Missions"
HTML_FILE = os.path.join(os.path.dirname(__file__), "index.html")
TODAY = datetime.now()

def parse_fm(fp):
    d = {}
    try:
        t = open(fp).read()
        if t.startswith('---'):
            p = t.split('---', 2)
            if len(p) >= 3:
                k, lst = None, []
                for ln in p[1].strip().split('\n'):
                    if ln.strip().startswith('- '):
                        if k: lst.append(ln.strip()[2:].strip())
                    elif ':' in ln:
                        if k and lst: d[k] = lst[0] if len(lst)==1 else ', '.join(lst); lst = []
                        kk, v = ln.split(':', 1)
                        k = kk.strip(); v = v.strip().strip('"').strip("'")
                        if v: d[k] = v; k = None
                if k and lst: d[k] = lst[0] if len(lst)==1 else ', '.join(lst)
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
        h.append({'reg': d.get('registration', os.path.basename(f).replace('.md','')), 'loc': d.get('location','UNK'), 'status': st, 'mission': d.get('current_mission',''), 'note': d.get('note','')})
    print(f"✅ Loaded {len(h)} helicopters")
    return h

def load_flights():
    fl, fy = [], {}
    try:
        t = open(FLIGHTS_FILE).read()
        ts = TODAY.strftime("%Y-%m-%d")
        for ln in t.split('\n'):
            if ln.startswith(ts) and '|' in ln:
                p = [x.strip() for x in ln.split('|')]
                if len(p) >= 4:
                    r = 'HZHC' + p[1].replace('HC','') if not p[1].startswith('HZ') else p[1]
                    fl.append({'reg': r, 'mission': p[2], 'pilot': p[3]})
                    fy[r] = p[3]
    except: pass
    print(f"✅ Loaded {len(fl)} flights")
    return fl, fy

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
            m.append({'title': t, 'date': d.get('date',''), 'endDate': d.get('endDate', d.get('date','')), 'status': d.get('status','pending'), 'helicopters': d.get('Helicopter',''), 'pilots': d.get('Pilots','')})
    m.sort(key=lambda x: x['date'] if x['date'] else 'zzzz')
    print(f"✅ Loaded {len(m)} missions")
    return m

def build_fleet_js(helis, fy):
    L = ["const fleet = ["]
    cnt = {'parked':0, 'flying':0, 'maint':0}
    for h in helis:
        st = 'flying' if h['reg'] in fy else h['status']
        cnt[st] = cnt.get(st,0) + 1
        e = f'  {{ reg: "{h["reg"]}", loc: "{h["loc"]}", status: "{st}"'
        if h['note']: e += f', note: "{h["note"]}"'
        if h['mission']: e += f', mission: "{h["mission"]}"'
        if h['reg'] in fy: e += f', pilot: "{fy[h["reg"]]}"'
        L.append(e + ' },')
    L.append("];")
    print(f"✅ Fleet: {cnt['parked']} serviceable, {cnt['flying']} flying, {cnt['maint']} maint")
    return '\n'.join(L)

def build_flights_html():
    L = []
    try:
        t = open(FLIGHTS_FILE).read()
        ts = TODAY.strftime("%Y-%m-%d")
        for ln in t.split('\n'):
            if ln.startswith('## '): L.append(f'  <h4>{ln[3:].strip()}</h4>')
            elif '|' in ln and 'HC' in ln and not ln.startswith('#'):
                p = [x.strip() for x in ln.split('|')]
                if len(p) >= 4:
                    r = p[1].replace('HZHC','HC') if 'HZ' in p[1] else p[1]
                    cl = "flight-row today" if p[0]==ts else "flight-row"
                    L.append(f'  <div class="{cl}"><span class="reg">{r}</span><span class="info">{p[2]}</span><span class="pilot">{p[3]}</span></div>')
    except: pass
    return '\n'.join(L) if L else '  <div>No flights</div>'

def build_currency_html(curr):
    L = []
    next_mo = (TODAY.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_mo_end = (next_mo + timedelta(days=32)).replace(day=1)
    
    # Competency - 12 months from last check, show due next month
    comp_due = []
    for c in curr:
        cp = c.get('competency','')
        if cp:
            try:
                cd = datetime.strptime(cp, "%Y-%m-%d")
                exp = cd.replace(year=cd.year+1)
                if next_mo <= exp < next_mo_end:
                    comp_due.append((c['name'], exp.strftime("%d %b")))
            except: pass
    L.append('  <h4>Competency Checks</h4>')
    if comp_due:
        for n, d in comp_due:
            L.append(f'  <div class="alert warn">⚠️ {next_mo.strftime("%B")} — {n} (due {d})</div>')
    else:
        L.append(f'  <div class="alert ok">✅ {next_mo.strftime("%B")} — nobody due</div>')
    
    # REMS - 6 months, only if they have a date
    rems_issues = []
    for c in curr:
        r = c.get('rems','')
        if r:
            try:
                rd = datetime.strptime(r, "%Y-%m")
                mo = (TODAY.year-rd.year)*12 + (TODAY.month-rd.month)
                if mo > 6: rems_issues.append((c['name'], rd.strftime("%B %Y"), 'danger'))
                elif mo >= 5: rems_issues.append((c['name'], rd.strftime("%B %Y"), 'warn'))
            except: pass
    if rems_issues:
        L.append('  <h4>30-Min REMS (6 month cycle)</h4>')
        for n,d,lv in sorted(rems_issues, key=lambda x: x[2]!='danger'):
            L.append(f'  <div class="alert {lv}">{"🔴" if lv=="danger" else "⚠️"} {n} — expired {d}</div>')
    
    # Medical - 12 months from check date
    med_issues = []
    for c in curr:
        m = c.get('medical','')
        if m:
            try:
                md = datetime.strptime(m, "%Y-%m-%d")
                exp = md.replace(year=md.year+1)
                days = (exp - TODAY).days
                if days < 0: med_issues.append((c['name'], exp.strftime("%B %Y"), 'danger'))
                elif days < 60: med_issues.append((c['name'], exp.strftime("%B"), 'warn'))
            except: pass
    if med_issues:
        L.append('  <h4>Medical Certificate (12 month validity)</h4>')
        for n,d,lv in sorted(med_issues, key=lambda x: x[2]!='danger'):
            L.append(f'  <div class="alert {lv}">{"🔴" if lv=="danger" else "⚠️"} {n} — {d}</div>')
    
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
    mn, mx, td = datetime(2025,10,1), datetime(2026,12,31), 0
    td = (mx-mn).days
    def pos(s,e): return round(((max(s,mn)-mn).days/td)*100,1), max(round(((min(e,mx)-max(s,mn)).days/td)*100,1), 1.2)
    def fdt(s,e):
        if s==e: return s.strftime("%-d %b")
        elif s.month==e.month: return f"{s.day}-{e.strftime('%-d %b')}"
        return f"{s.strftime('%-d %b')} - {e.strftime('%-d %b')}"
    def ovl(a,b): return not (a['e']+timedelta(days=2) < b['s'] or b['e']+timedelta(days=2) < a['s'])
    def pack(evs):
        lanes = []
        for ev in evs:
            placed = False
            for lane in lanes:
                if not any(ovl(ev,e) for e in lane): lane.append(ev); placed=True; break
            if not placed: lanes.append([ev])
        return lanes
    lanes = pack(dated)
    above, below = lanes[::2], lanes[1::2]
    L = ['    <div class="timeline-wrapper">']
    if tbd:
        L.append('    <div class="tbd-sidebar">')
        L.append('      <div class="tbd-header">📋 Dates TBD</div>')
        for m in tbd: L.append(f'      <div class="tbd-item" data-name="{m["title"]}" data-status="pending" data-dates="TBD" data-aircraft="TBD" data-pilots="TBD" onclick="showEventPopup(this,event)">\n        {m["title"]}\n      </div>')
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
    for lane in above:
        L.append('        <div class="lane">')
        for m in sorted(lane, key=lambda x: x['s']): L.append(bar(m))
        L.append('        </div>')
    L.append('      </div>')
    L.append('      <div class="timeline-axis">')
    L.append('        <div class="axis-line"></div>')
    c = mn
    while c <= mx:
        L.append(f'        <div class="month-marker" style="left:{round(((c-mn).days/td)*100,1)}%;">{c.strftime("%b %Y")}</div>')
        c = (c.replace(day=1)+timedelta(days=32)).replace(day=1)
    if mn <= TODAY <= mx: L.append(f'      <div class="today-marker" style="left:{round(((TODAY-mn).days/td)*100,1)}%;"><span>Today</span></div>')
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
    fl, fy = load_flights()
    c = load_currency()
    m = load_missions()
    html = open(HTML_FILE).read()
    html = update(html, build_fleet_js(h, fy), build_flights_html(), build_currency_html(c), build_timeline(m))
    open(HTML_FILE, 'w').write(html)
    print(f"\n✅ Done!")

if __name__ == "__main__": main()
