#!/bin/bash

# ==============================================================================
# ODEV Documentation Recorder
# This script eases the creation of animated GIFs for odev commands.
# Usage: ./record.sh "odev <command> <args>"
# ==============================================================================

FULL_CMD=$1
ROWS_OVERRIDE=$2
COLS_OVERRIDE=$3
NAME_OVERRIDE=$4

if [ -z "$FULL_CMD" ]; then
    echo "Usage: ./record.sh \"command to record\" [ROWS] [COLS] [NAME] [--cut] [--fast] [--instant]"
    echo "Example: ./record.sh \"odev list -a\" 30 140 list_all"
    echo "Example: ./record.sh \"odev ls\" 20 140 ls_cut --cut"
    exit 1
fi

# Configuration for a "premium" documentation look
ROWS=${ROWS_OVERRIDE:-20}
COLS=${COLS_OVERRIDE:-140}
TYPING_DELAY=0.05

# Check for flags in arguments
SHOULD_CUT=false
for arg in "$@"; do
    if [ "$arg" == "--cut" ]; then
        SHOULD_CUT=true
        if [ "$ROWS" == "--cut" ]; then ROWS=20; fi
        if [ "$COLS" == "--cut" ]; then COLS=140; fi
    elif [ "$arg" == "--fast" ]; then
        TYPING_DELAY=0.02
        if [ "$ROWS" == "--fast" ]; then ROWS=20; fi
        if [ "$COLS" == "--fast" ]; then COLS=140; fi
    elif [ "$arg" == "--instant" ]; then
        TYPING_DELAY=0
        if [ "$ROWS" == "--instant" ]; then ROWS=20; fi
        if [ "$COLS" == "--instant" ]; then COLS=140; fi
    fi
done

if [ "$SHOULD_CUT" = true ]; then
    # We leave 2 rows for the prompt and potential empty line at end
    LIMIT=$((ROWS - 2))
    echo "::: Output will be visually truncated to $LIMIT lines in the GIF"
fi

FONT_SIZE=16
SPEED=1.5

# Extract the subcommand for the filename
if [ -n "$NAME_OVERRIDE" ] && [ "$NAME_OVERRIDE" != "--cut" ] && [ "$NAME_OVERRIDE" != "--fast" ] && [ "$NAME_OVERRIDE" != "--instant" ]; then
    NAME="$NAME_OVERRIDE"
elif [[ $FULL_CMD == odev* ]]; then
    NAME=$(echo $FULL_CMD | awk '{print $2}')
else
    NAME=$(echo $FULL_CMD | awk '{print $1}')
fi
NAME=$(echo $NAME | tr -cd '[:alnum:]_-')

# Find repo root to ensure paths work regardless of where the script is called.
# Fallback to the script's parent directory if not in a git repo (e.g. running from a temp folder).
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$(cd "$(dirname "$0")/.." && pwd)")
CAST_FILE="${REPO_ROOT}/docs/static/gifs/${NAME}.cast"
GIF_FILE="${REPO_ROOT}/docs/static/gifs/${NAME}.gif"

mkdir -p "${REPO_ROOT}/docs/static/gifs"

# ANSI colors for the simulated prompt in the GIF
C_GREEN="\x1b[32m"
C_BLUE="\x1b[34m"
C_RESET="\x1b[0m"
C_BOLD="\x1b[1m"

DISPLAY_PROMPT="${C_BOLD}${C_GREEN}odev${C_RESET}@${C_BOLD}${C_BLUE}odoo${C_RESET}$ "

# Configuration for the recording environment
TMP_RC=$(mktemp)
cat << EOF > "$TMP_RC"
export PS1="${DISPLAY_PROMPT}"
export TERM=xterm-256color
export COLUMNS=$COLS
export LINES=$ROWS
# Function to simulate typing
type_cmd() {
    local text="\$1"
    local delay=\${TYPING_DELAY:-0.1}
    for (( i=0; i<\${#text}; i++ )); do
        echo -n "\${text:\$i:1}"
        [ "\$delay" != "0" ] && sleep \$delay
    done
}
EOF

echo "::: Recording command with premium look: $FULL_CMD"

# We use stty to force the PTY size and --cols/--rows for asciinema.
# We use a temporary script to avoid quoting issues with complex commands.
# We pass the command via an environment variable to avoid nesting quotes.
RECORD_SCRIPT=$(mktemp)
export RECORD_CMD="$FULL_CMD"
# Use a user-friendly name for internal simulation scripts in the GIF
export TYPING_CMD="$RECORD_CMD"
if [[ "$RECORD_CMD" == *"simulate_setup.py"* ]]; then
    export TYPING_CMD="odev setup"
fi
export ROWS=$ROWS
export COLS=$COLS
export TMP_RC=$TMP_RC
export DISPLAY_PROMPT=$DISPLAY_PROMPT
export TYPING_DELAY=$TYPING_DELAY
cat << 'ERR_EOF' > "$RECORD_SCRIPT"
#!/bin/bash
stty rows $ROWS cols $COLS
source $TMP_RC
echo -n -e "${DISPLAY_PROMPT}"
type_cmd "$TYPING_CMD"
echo ""
python3 -c "import pty, sys, os; pty.spawn(['/bin/bash', '-c', os.environ['RECORD_CMD']])"
# Keep the final output visible for a moment before closing
sleep 2
ERR_EOF
chmod +x "$RECORD_SCRIPT"

# Record the session
# We use --rows/--cols to ensure asciinema knows the dimensions
asciinema rec --overwrite --rows "$ROWS" --cols "$COLS" -c "$RECORD_SCRIPT" "$CAST_FILE"

# Visual Truncation (Post-processing)
if [ "$SHOULD_CUT" = true ]; then
    echo "::: Cutting cast file to $LIMIT lines..."
    TMP_CAST=$(mktemp)
    python3 -c "
import json, sys
limit = int(sys.argv[1])
count = 0
header = True
with open(sys.argv[2], 'r') as f:
    for line in f:
        if header:
            print(line, end='')
            header = False
            continue
        try:
            data = json.loads(line)
            if data[1] == 'o':
                print(line, end='')
                count += data[2].count('\n')
                if count >= limit:
                    break
                continue
            print(line, end='')
        except:
            print(line, end='')
" "$LIMIT" "$CAST_FILE" > "$TMP_CAST"
    mv "$TMP_CAST" "$CAST_FILE"
fi

# Anonymize: replace local username with 'odev'
echo "::: Anonymizing output (crupuk -> odev)..."
sed -i 's/crupuk/odev/g' "$CAST_FILE"

rm "$TMP_RC" "$RECORD_SCRIPT"

echo "::: Recorded to $CAST_FILE"
echo "::: Converting to GIF with agg (Premium settings)..."
# agg options: --font-size, --speed, --theme, --rows, --cols
# We add --last-frame-duration 2 to keep the final state visible
agg --font-size "$FONT_SIZE" --speed "$SPEED" --theme "monokai" --rows "$ROWS" --cols "$COLS" --last-frame-duration 2 "$CAST_FILE" "$GIF_FILE"

echo "::: Successfully generated $GIF_FILE"

# Cleanup and final output
rm -f "$CAST_FILE"
echo "::: Finished: $GIF_FILE"
