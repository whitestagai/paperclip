# Convert a display name to a filesystem-safe slug.
# Examples:
#   "Bild & Video"       → "bild-und-video"
#   "Müll-Räumer"        → "muell-raeumer"
#   "  Online Recherche " → "online-recherche"

slug_from_name() {
  local name="$1"
  name=$(echo "$name" | sed \
    -e 's/ä/ae/g' -e 's/ö/oe/g' -e 's/ü/ue/g' -e 's/ß/ss/g' \
    -e 's/Ä/Ae/g' -e 's/Ö/Oe/g' -e 's/Ü/Ue/g')
  name=$(echo "$name" | sed 's/&/und/g')
  name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
  name=$(echo "$name" | sed 's/[^a-z0-9]/-/g')
  name=$(echo "$name" | sed 's/--*/-/g')
  name=$(echo "$name" | sed 's/^-//' | sed 's/-$//')
  echo "$name"
}

# Write _index.md mapping (slug ↔ uuid ↔ company)
# Variadic: write_slug_index <output-file> <company-slug-1> <agents-json-1> <company-slug-2> <agents-json-2> ...
write_slug_index() {
  local out="$1"; shift
  {
    echo "# Agent Slug-Index"
    echo
    echo "Auto-generiert vom \`agent-learning-trigger.sh\`. Bitte nicht von Hand editieren —"
    echo "wird beim nächsten Lauf überschrieben."
    echo
    echo "| Slug | UUID | Company |"
    echo "|---|---|---|"
    while [[ $# -gt 0 ]]; do
      local company_slug="$1"; shift
      local agents_json="$1"; shift
      echo "$agents_json" | jq -r '.[] | [.name, .id] | @tsv' \
        | while IFS=$'\t' read -r name id; do
          local slug
          slug=$(slug_from_name "$name")
          echo "| ${slug} | \`${id}\` | ${company_slug} |"
        done
    done
  } > "$out"
}
