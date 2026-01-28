#!/usr/bin/env bash
# generate.sh — Refreshes the fleet map from Obsidian THC Vault.
# Updates: fleet array, legend, pilot currency, flight schedule, dates.
# Source of truth: Obsidian THC Vault (helicopters, pilots, flights).
# Run before deploy: bash generate.sh && git add -A && git commit -m "Update from Obsidian" && git push

set -euo pipefail

VAULT="/Users/willlawrence/Library/Mobile Documents/iCloud~md~obsidian/Documents/THC Vault"
HELIS_DIR="$VAULT/Helicopters"
PILOTS_DIR="$VAULT/Pilots"
FLIGHTS_FILE="$VAULT/Flights Schedule.md"
HTML="$(dirname "$0")/index.html"

TODAY_DISPLAY=$(date "+%-d %b %Y")
TODAY_UPPER=$(date "+%-d %b %Y" | tr '[:lower:]' '[:upper:]')
THIS_YM=$(date +%Y-%m)
NEXT_YM=$(date -v+1m +%Y-%m 2>/dev/null || date -d "+1 month" +%Y-%m)
THREE_YM=$(date -v+3m +%Y-%m 2>/dev/null || date -d "+3 months" +%Y-%m)
THIS_MONTH=$(date +%Y-%m-01)
THREE_MONTHS=$(date -v+3m +%Y-%m-01 2>/dev/null || date -d "+3 months" +%Y-%m-01)

###############################################################################
# 1. FLEET ARRAY
###############################################################################
fleet_js=""
count_parked=0
count_flying=0
count_maint=0

for f in "$HELIS_DIR"/HZHC*.md; do
  [ -f "$f" ] || continue

  reg=$(grep "^registration:" "$f" | sed 's/^registration:[[:space:]]*//')
  loc=$(grep "^location:" "$f" | sed 's/^location:[[:space:]]*//')
  status_raw=$(grep "^status:" "$f" | sed 's/^status:[[:space:]]*//')
  mission=$(grep "^mission:" "$f" | sed 's/^mission:[[:space:]]*//')

  [ -z "$reg" ] && continue

  status_lower=$(echo "$status_raw" | tr '[:upper:]' '[:lower:]')
  note=""
  map_status="parked"

  if echo "$status_lower" | grep -qi "maintenance\|unserviceable"; then
    map_status="maint"
    note=$(echo "$status_raw" | sed -n 's/^[^-]*-[[:space:]]*//p')
  elif echo "$status_lower" | grep -qi "flying"; then
    map_status="flying"
  fi

  # Capture any extra info after " - "
  if [ -z "$note" ] && echo "$status_raw" | grep -q " - "; then
    note=$(echo "$status_raw" | sed 's/^[^-]*-[[:space:]]*//')
  fi

  case "$map_status" in
    parked) count_parked=$((count_parked + 1)) ;;
    flying) count_flying=$((count_flying + 1)) ;;
    maint)  count_maint=$((count_maint + 1)) ;;
  esac

  entry="  { reg: \"${reg}\", loc: \"${loc}\", status: \"${map_status}\""
  [ -n "$note" ] && entry+=", note: \"$(echo "$note" | sed 's/"/\\"/g')\""
  [ -n "$mission" ] && entry+=", mission: \"$(echo "$mission" | sed 's/"/\\"/g')\""
  entry+=" },"
  fleet_js+="${entry}\n"
done

fleet_block="const fleet = [\n${fleet_js}];"

###############################################################################
# 2b. FSR NOTE — Obsidian is the master. No hardcoded list.
# The fleet IS whatever HZHC*.md files exist. Nothing else.
###############################################################################
fsr_note=""

###############################################################################
# 3. PILOT CURRENCY
###############################################################################
# Month names
THIS_MONTH_NAME=$(date "+%B")
NEXT_MONTH_NAME=$(date -v+1m "+%B" 2>/dev/null || date -d "+1 month" "+%B")

# Collect per-pilot data into arrays
comp_overdue_names="" comp_this_names="" comp_next_names=""
rems_overdue_list="" rems_this_list="" rems_next_list=""

for dir in "$PILOTS_DIR"/*/; do
  name=$(basename "$dir")
  md="$dir/${name}.md"
  [ -f "$md" ] || continue

  rems=$(grep "^30 Mins REMS:" "$md" | head -1 | sed 's/^30 Mins REMS:[[:space:]]*//')
  comp=$(grep "^Last Competency Check:" "$md" | head -1 | sed 's/^Last Competency Check:[[:space:]]*//')
  base_month=$(grep "^Base Month:" "$md" | head -1 | sed 's/^Base Month:[[:space:]]*//')

  # Use full name for display
  fullname="$name"

  # REMS — date stored is when they LAST FLEW (issue date). Expires +6 months.
  if [ -n "$rems" ] && [ "$rems" != "NA" ] && [ "$rems" != "N/A" ]; then
    rems_ym="${rems:0:7}"
    # Calculate expiry: last flew + 6 months
    expiry_ym=$(date -jf "%Y-%m-%d" -v+6m "${rems_ym}-01" "+%Y-%m" 2>/dev/null || echo "")
    last_flew_fmt=$(date -jf "%Y-%m-%d" "${rems_ym}-01" "+%B %Y" 2>/dev/null || echo "$rems_ym")
    if [[ "$expiry_ym" < "$THIS_YM" ]]; then
      rems_overdue_list="${rems_overdue_list}${fullname} — last flew ${last_flew_fmt}|"
    elif [[ "$expiry_ym" == "$THIS_YM" ]]; then
      rems_this_list="${rems_this_list}${fullname} — last flew ${last_flew_fmt}|"
    elif [[ "$expiry_ym" == "$NEXT_YM" ]]; then
      rems_next_list="${rems_next_list}${fullname} — last flew ${last_flew_fmt}|"
    fi
  fi

  # Competency (annual from last check)
  if [ -n "$comp" ]; then
    comp_year=$(echo "$comp" | cut -d- -f1)
    comp_month=$(echo "$comp" | cut -d- -f2)
    next_due="${comp_year}-${comp_month}-01"
    next_due=$(date -jf "%Y-%m-%d" -v+1y "$next_due" "+%Y-%m-%d" 2>/dev/null || echo "$((comp_year+1))-${comp_month}-01")
    next_due_ym="${next_due:0:7}"
    if [[ "$next_due_ym" < "$THIS_YM" ]]; then
      comp_overdue_names="${comp_overdue_names}${fullname}|"
    elif [[ "$next_due_ym" == "$THIS_YM" ]]; then
      comp_this_names="${comp_this_names}${fullname}|"
    elif [[ "$next_due_ym" == "$NEXT_YM" ]]; then
      comp_next_names="${comp_next_names}${fullname}|"
    fi
  fi
done

# Build currency HTML — month-by-month style
currency=""
currency+="  <h4>Competency Checks</h4>\n"

# This month
if [ -n "$comp_this_names" ]; then
  names=$(echo "${comp_this_names%|}" | tr '|' ', ')
  currency+="  <div class=\"alert warn\">⚠️ ${THIS_MONTH_NAME} — ${names}</div>\n"
else
  currency+="  <div class=\"alert ok\">✅ ${THIS_MONTH_NAME} — nobody due</div>\n"
fi

# Next month
if [ -n "$comp_next_names" ]; then
  names=$(echo "${comp_next_names%|}" | tr '|' ', ')
  currency+="  <div class=\"alert warn\">⚠️ ${NEXT_MONTH_NAME} — ${names}</div>\n"
else
  currency+="  <div class=\"alert ok\">✅ ${NEXT_MONTH_NAME} — nobody due</div>\n"
fi

# Overdue
if [ -n "$comp_overdue_names" ]; then
  names=$(echo "${comp_overdue_names%|}" | tr '|' ', ')
  currency+="  <div class=\"alert danger\">🔴 Overdue: ${names}</div>\n"
fi

currency+="  <h4>30-Min REMS (Instrument Currency — 6 month cycle)</h4>\n"

# REMS this month
if [ -n "$rems_this_list" ]; then
  IFS='|' read -ra items <<< "${rems_this_list%|}"
  for item in "${items[@]}"; do
    currency+="  <div class=\"alert warn\">⚠️ Due now (${THIS_MONTH_NAME:0:3}): ${item}</div>\n"
  done
fi

# REMS next month
if [ -n "$rems_next_list" ]; then
  IFS='|' read -ra items <<< "${rems_next_list%|}"
  for item in "${items[@]}"; do
    currency+="  <div class=\"alert warn\">⚠️ Due next month (${NEXT_MONTH_NAME:0:3}): ${item}</div>\n"
  done
fi

# REMS overdue
if [ -n "$rems_overdue_list" ]; then
  names=$(echo "${rems_overdue_list%|}" | sed 's/|/ · /g')
  currency+="  <div class=\"alert danger\">🔴 Overdue: ${names}</div>\n"
fi

# All clear
if [ -z "$rems_this_list" ] && [ -z "$rems_next_list" ] && [ -z "$rems_overdue_list" ]; then
  currency+="  <div class=\"alert ok\">✅ All REMS current</div>\n"
fi

###############################################################################
# 4. FLIGHT SCHEDULE
###############################################################################
flights_html=""
report_period=""

if [ -f "$FLIGHTS_FILE" ]; then
  # Extract report period from frontmatter
  report_period=$(grep "^report_period:" "$FLIGHTS_FILE" | sed 's/^report_period:[[:space:]]*//')

  # Parse the file: section headers become h4, flight lines become rows
  current_section=""
  while IFS= read -r line; do
    # Skip frontmatter, comments, blank lines
    [[ "$line" =~ ^---$ ]] && continue
    [[ "$line" =~ ^report_period: ]] && continue
    [[ "$line" =~ ^#\ Flights ]] && continue
    [[ "$line" =~ ^\<\!-- ]] && continue
    [[ -z "$line" ]] && continue

    # Section header (## Title)
    if [[ "$line" =~ ^##\  ]]; then
      current_section="${line#\#\# }"
      flights_html+="  <h4>${current_section}</h4>\n"
      continue
    fi

    # Flight line: DATE | REG | MISSION | PILOT | FLAGS
    if [[ "$line" =~ \| ]]; then
      IFS='|' read -ra parts <<< "$line"
      reg=$(echo "${parts[1]:-}" | xargs)
      mission=$(echo "${parts[2]:-}" | xargs)
      pilot=$(echo "${parts[3]:-}" | xargs)
      flags=$(echo "${parts[4]:-}" | xargs | tr '[:upper:]' '[:lower:]')

      row_class=""
      [[ "$flags" == *today* ]] && row_class=" today"

      flights_html+="  <div class=\"flight-row${row_class}\"><span class=\"reg\">${reg}</span><span class=\"info\">${mission}</span><span class=\"pilot\">${pilot}</span></div>\n"
    fi
  done < "$FLIGHTS_FILE"

  echo "✅ Flight schedule parsed from Obsidian"
else
  echo "⚠️  No Flights Schedule.md found — skipping flight schedule"
fi

###############################################################################
# 5. APPLY TO HTML
###############################################################################

# Fleet array
if grep -q "// FLEET_START" "$HTML"; then
  awk -v new="$fleet_block" '
    /\/\/ FLEET_START/ { print; printf "%s\n", new; skip=1; next }
    /\/\/ FLEET_END/ { skip=0 }
    !skip { print }
  ' "$HTML" > "${HTML}.tmp" && mv "${HTML}.tmp" "$HTML"
  echo "✅ Fleet array updated ($((count_parked + count_flying + count_maint)) helicopters)"
else
  echo "⚠️  Missing // FLEET_START marker"
fi

# Legend date (counts are JS-computed from fleet array automatically)
if grep -q "<!-- LEGEND_DATE -->" "$HTML"; then
  sed -i '' "s|<!-- LEGEND_DATE -->.*<!-- /LEGEND_DATE -->|<!-- LEGEND_DATE -->${TODAY_DISPLAY}<!-- /LEGEND_DATE -->|" "$HTML"
  echo "✅ Legend date updated (fleet: S:${count_parked} F:${count_flying} M:${count_maint})"
else
  echo "⚠️  Missing <!-- LEGEND_DATE --> marker"
fi

# Flight schedule
if [ -n "$flights_html" ] && grep -q "<!-- FLIGHTS_START -->" "$HTML"; then
  awk -v new="$flights_html" '
    /<!-- FLIGHTS_START -->/ { print; printf "%s", new; skip=1; next }
    /<!-- FLIGHTS_END -->/ { skip=0 }
    !skip { print }
  ' "$HTML" > "${HTML}.tmp" && mv "${HTML}.tmp" "$HTML"
  echo "✅ Flight schedule updated"
fi

# Report period
if [ -n "$report_period" ] && grep -q "<!-- REPORT_PERIOD -->" "$HTML"; then
  sed -i '' "s|<!-- REPORT_PERIOD -->.*<!-- /REPORT_PERIOD -->|<!-- REPORT_PERIOD -->${report_period}<!-- /REPORT_PERIOD -->|" "$HTML"
  echo "✅ Report period: ${report_period}"
fi

# Currency
if grep -q "<!-- CURRENCY_START -->" "$HTML"; then
  awk -v new="$currency" '
    /<!-- CURRENCY_START -->/ { print; printf "%s\n", new; skip=1; next }
    /<!-- CURRENCY_END -->/ { skip=0 }
    !skip { print }
  ' "$HTML" > "${HTML}.tmp" && mv "${HTML}.tmp" "$HTML"
  echo "✅ Pilot currency updated"
else
  echo "⚠️  Missing <!-- CURRENCY_START --> marker"
fi

# Last updated timestamp
UPDATED_STAMP=$(date "+%-d %b %Y %H:%M")
if grep -q "<!-- LAST_UPDATED -->" "$HTML"; then
  sed -i '' "s|<!-- LAST_UPDATED -->.*<!-- /LAST_UPDATED -->|<!-- LAST_UPDATED -->${UPDATED_STAMP}<!-- /LAST_UPDATED -->|" "$HTML"
  echo "✅ Last updated: ${UPDATED_STAMP}"
fi

# Title tag
sed -i '' "s|<title>Fleet Map — .*</title>|<title>Fleet Map — ${TODAY_DISPLAY}</title>|" "$HTML"
echo "✅ Page title updated"

echo ""
echo "Done. Review with: open https://willslawrence.github.io/thc-ops-map/"
