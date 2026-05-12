# Move files older than $2 days from $1 into $1/_archive/.
# Skips MEMORY.md, .gitkeep, dotfiles. Skips the _archive dir itself.

decay_archive_dir() {
  local dir="$1" days="$2"
  [[ -d "$dir" ]] || return 0
  mkdir -p "$dir/_archive"
  find "$dir" -maxdepth 1 -type f -name '*.md' -mtime "+${days}" \
    ! -name 'MEMORY.md' ! -name '.*' \
    -exec mv {} "$dir/_archive/" \;
}

decay_run() {
  # $1 = vault root, $2 = knowledge dir, $3 = agents dir,
  # $4 = knowledge_archive_after_days, $5 = lessons_archive_after_days
  local root="$1" k_dir="$2" a_dir="$3" k_days="$4" l_days="$5"

  if [[ -d "$root/$k_dir" ]]; then
    for d in "$root/$k_dir"/*/; do
      decay_archive_dir "$d" "$k_days"
    done
  fi

  if [[ -d "$root/$a_dir" ]]; then
    for co_dir in "$root/$a_dir"/*/; do
      [[ -d "$co_dir" ]] || continue
      for ag_dir in "$co_dir"*/; do
        [[ -d "${ag_dir}lessons" ]] && decay_archive_dir "${ag_dir}lessons" "$l_days"
      done
    done
  fi
}
