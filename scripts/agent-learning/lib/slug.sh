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
