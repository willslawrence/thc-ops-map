#!/usr/bin/env bash
# generate-currency.sh — Reads pilot YAML from Obsidian THC Vault
# and regenerates the Pilot Currency + REMS alerts in index.html.
# Run before each deploy / commit.

set -euo pipefail

VAULT="/Users/willlawrence/Library/Mobile Documents/iCloud~md~obsidian/Documents/THC Vault"
PILOTS_DIR="$VAULT/Pilots"
HTML="$(dirname "$0")/index.html"
TODAY=$(date +%Y-%m-%d)
THIS_MONTH=$(date +%Y-%m-01)
# "Next month" for "due soon" window
NEXT_MONTH=$(date -v+1m +%Y-%m-01 2>/dev/null || date -d "+1 month" +%Y-%m-01)
TWO_MONTHS=$(date -v+2m +%Y-%m-01 2>/dev/null || date -d "+2 months" +%Y-%m-01)
THREE_MONTHS=$(date -v+3m +%Y-%m-01 2>/dev/null || date -d "+3 months" +%Y-%m-01)

rems_alerts=""
comp_alerts=""
overdue_rems=""
due_now_rems=""
due_soon_rems=""
current_rems=""
comp_due=""
comp_overdue=""

for dir in "$PILOTS_DIR"/*/; do
  name=$(basename "$dir")
  md="$dir/${name}.md"
  [ -f "$md" ] || continue

  # Parse fields
  rems=$(grep "^30 Mins REMS:" "$md" | head -1 | sed 's/^30 Mins REMS:[[:space:]]*//')
  base_month=$(grep "^Base Month:" "$md" | head -1 | sed 's/^Base Month:[[:space:]]*//')
  comp=$(grep "^Last Competency Check:" "$md" | head -1 | sed 's/^Last Competency Check:[[:space:]]*//')

  # Extract last name for display
  last=$(echo "$name" | awk '{print $NF}')

  # --- REMS check ---
  if [ -n "$rems" ] && [ "$rems" != "NA" ] && [ "$rems" != "N/A" ]; then
    rems_fmt=$(date -jf "%Y-%m-%d" "$rems" "+%b %Y" 2>/dev/null || echo "$rems")
    if [[ "$rems" < "$THIS_MONTH" ]]; then
      overdue_rems="${overdue_rems}${last} (${rems_fmt}), "
    elif [[ "$rems" < "$NEXT_MONTH" ]]; then
      due_now_rems="${due_now_rems}${last} (${rems_fmt}), "
    elif [[ "$rems" < "$THREE_MONTHS" ]]; then
      due_soon_rems="${due_soon_rems}${last} (${rems_fmt}), "
    else
      current_rems="${current_rems}${last}, "
    fi
  elif [ -z "$rems" ] || [ "$rems" = "NA" ] || [ "$rems" = "N/A" ]; then
    # No REMS data — skip or flag
    :
  fi

  # --- Competency check (annual, based on Base Month) ---
  if [ -n "$comp" ]; then
    # Competency is due in the base month each year
    # Check if last comp + 12 months is before today
    comp_year=$(echo "$comp" | cut -d- -f1)
    next_comp_year=$((comp_year + 1))
    comp_month=$(echo "$comp" | cut -d- -f2)
    next_due="${next_comp_year}-${comp_month}-01"
    next_due_fmt=$(date -jf "%Y-%m-%d" "$next_due" "+%b %Y" 2>/dev/null || echo "$next_due")
    if [[ "$next_due" < "$THIS_MONTH" ]]; then
      comp_overdue="${comp_overdue}${last} (${next_due_fmt}), "
    elif [[ "$next_due" < "$THREE_MONTHS" ]]; then
      comp_due="${comp_due}${last} (${next_due_fmt}), "
    fi
  fi
done

# Build HTML alerts
alerts=""

# Competency section
alerts+="  <h4>Pilot Currency</h4>\n"
if [ -n "$comp_overdue" ]; then
  comp_overdue="${comp_overdue%, }"
  alerts+="  <div class=\"alert danger\">🔴 Competency overdue: ${comp_overdue}</div>\n"
fi
if [ -n "$comp_due" ]; then
  comp_due="${comp_due%, }"
  alerts+="  <div class=\"alert warn\">⚠️ Competency due soon: ${comp_due}</div>\n"
fi
if [ -z "$comp_overdue" ] && [ -z "$comp_due" ]; then
  alerts+="  <div class=\"alert ok\">✅ Competency — all current</div>\n"
fi

# REMS section
alerts+="  <h4>30-Min REMS (Instrument Currency)</h4>\n"
if [ -n "$overdue_rems" ]; then
  overdue_rems="${overdue_rems%, }"
  alerts+="  <div class=\"alert danger\">🔴 Overdue: ${overdue_rems}</div>\n"
fi
if [ -n "$due_now_rems" ]; then
  due_now_rems="${due_now_rems%, }"
  alerts+="  <div class=\"alert warn\">⚠️ Due now: ${due_now_rems}</div>\n"
fi
if [ -n "$due_soon_rems" ]; then
  due_soon_rems="${due_soon_rems%, }"
  alerts+="  <div class=\"alert warn\">⚠️ Due next month: ${due_soon_rems}</div>\n"
fi
if [ -z "$overdue_rems" ] && [ -z "$due_now_rems" ] && [ -z "$due_soon_rems" ]; then
  alerts+="  <div class=\"alert ok\">✅ All REMS current</div>\n"
fi

# Replace the currency section in index.html
# Markers: <!-- CURRENCY_START --> and <!-- CURRENCY_END -->
if grep -q "<!-- CURRENCY_START -->" "$HTML"; then
  # Use awk to replace between markers
  awk -v new="$alerts" '
    /<!-- CURRENCY_START -->/ { print; printf "%s", new; skip=1; next }
    /<!-- CURRENCY_END -->/ { skip=0 }
    !skip { print }
  ' "$HTML" > "${HTML}.tmp" && mv "${HTML}.tmp" "$HTML"
  echo "✅ Currency alerts updated in index.html"
else
  echo "⚠️  No <!-- CURRENCY_START --> marker found in index.html."
  echo "    Add <!-- CURRENCY_START --> and <!-- CURRENCY_END --> markers around the currency section."
  echo ""
  echo "Generated alerts:"
  echo -e "$alerts"
fi
