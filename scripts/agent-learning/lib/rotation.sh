weekday_short() {
  # $1 = ISO weekday number (1=Mon..7=Sun)
  case "$1" in
    1) echo "mon" ;;
    2) echo "tue" ;;
    3) echo "wed" ;;
    4) echo "thu" ;;
    5) echo "fri" ;;
    6) echo "sat" ;;
    7) echo "sun" ;;
    *) return 1 ;;
  esac
}

weekday_short_today() {
  weekday_short "$(date +%u)"
}
