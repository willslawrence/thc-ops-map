#!/usr/bin/env bash
# generate.sh — Refreshes the fleet map from Obsidian THC Vault.
# Updates: fleet array, legend, pilot currency alerts, page date.
# Does NOT touch: ops plan flights, routes, or mission schedule.
# Run before deploy: bash generate.sh && git add -A && git commit -m "Update from Obsidian" && git push

set -euo pipefail

VAULT="/Users/willlawrence/Library/Mobile Documents/iCloud~md~obsidian/Documents/THC Vault"
HELIS_DIR="$VAULT/Helicopters"
PILOTS_DIR="$VAULT/Pilots"
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
# 3. PILOT CURRENCY
###############################################################################
overdue_rems="" due_now_rems="" due_soon_rems=""
comp_overdue="" comp_due=""

for dir in "$PILOTS_DIR"/*/; do
  name=$(basename "$dir")
  md="$dir/${name}.md"
  [ -f "$md" ] || continue

  rems=$(grep "^30 Mins REMS:" "$md" | head -1 | sed 's/^30 Mins REMS:[[:space:]]*//')
  comp=$(grep "^Last Competency Check:" "$md" | head -1 | sed 's/^Last Competency Check:[[:space:]]*//')

  last=$(echo "$name" | awk '{print $NF}')

  # REMS
  if [ -n "$rems" ] && [ "$rems" != "NA" ] && [ "$rems" != "N/A" ]; then
    rems_ym="${rems:0:7}"
    rems_fmt=$(date -jf "%Y-%m-%d" "${rems_ym}-01" "+%b %Y" 2>/dev/null || echo "$rems_ym")
    if [[ "$rems_ym" < "$THIS_YM" ]]; then
      overdue_rems="${overdue_rems}${last} (${rems_fmt}), "
    elif [[ "$rems_ym" == "$THIS_YM" ]]; then
      due_now_rems="${due_now_rems}${last} (${rems_fmt}), "
    elif [[ "$rems_ym" < "$THREE_YM" ]]; then
      due_soon_rems="${due_soon_rems}${last} (${rems_fmt}), "
    fi
  fi

  # Competency (annual)
  if [ -n "$comp" ]; then
    comp_year=$(echo "$comp" | cut -d- -f1)
    comp_month=$(echo "$comp" | cut -d- -f2)
    next_due="${comp_year}-${comp_month}-01"
    next_due=$(date -jf "%Y-%m-%d" -v+1y "$next_due" "+%Y-%m-%d" 2>/dev/null || echo "$((comp_year+1))-${comp_month}-01")
    next_due_fmt=$(date -jf "%Y-%m-%d" "$next_due" "+%b %Y" 2>/dev/null || echo "$next_due")
    if [[ "$next_due" < "$THIS_MONTH" ]]; then
      comp_overdue="${comp_overdue}${last} (${next_due_fmt}), "
    elif [[ "$next_due" < "$THREE_MONTHS" ]]; then
      comp_due="${comp_due}${last} (${next_due_fmt}), "
    fi
  fi
done

# Build currency HTML
currency=""
currency+="  <h4>Pilot Currency</h4>\n"
if [ -n "$comp_overdue" ]; then
  currency+="  <div class=\"alert danger\">🔴 Competency overdue: ${comp_overdue%, }</div>\n"
fi
if [ -n "$comp_due" ]; then
  currency+="  <div class=\"alert warn\">⚠️ Competency due soon: ${comp_due%, }</div>\n"
fi
if [ -z "$comp_overdue" ] && [ -z "$comp_due" ]; then
  currency+="  <div class=\"alert ok\">✅ Competency — all current</div>\n"
fi

currency+="  <h4>30-Min REMS (Instrument Currency)</h4>\n"
if [ -n "$overdue_rems" ]; then
  currency+="  <div class=\"alert danger\">🔴 Overdue: ${overdue_rems%, }</div>\n"
fi
if [ -n "$due_now_rems" ]; then
  currency+="  <div class=\"alert warn\">⚠️ Due this month: ${due_now_rems%, }</div>\n"
fi
if [ -n "$due_soon_rems" ]; then
  currency+="  <div class=\"alert warn\">⚠️ Due within 3 months: ${due_soon_rems%, }</div>\n"
fi
if [ -z "$overdue_rems" ] && [ -z "$due_now_rems" ] && [ -z "$due_soon_rems" ]; then
  currency+="  <div class=\"alert ok\">✅ All REMS current</div>\n"
fi

###############################################################################
# 4. APPLY TO HTML
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

# Title tag
sed -i '' "s|<title>Fleet Map — .*</title>|<title>Fleet Map — ${TODAY_DISPLAY}</title>|" "$HTML"
echo "✅ Page title updated"

echo ""
echo "Done. Review with: open https://willslawrence.github.io/thc-ops-map/"
