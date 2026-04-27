import logging
import os
import re


logger = logging.getLogger(__name__)


def clean_description(help_text):
    # Extract Title (Description block after ODEV <CMD>)
    match_desc = re.search(r"ODEV [^ \n]+\n\n(.*?)\n\n\s*Usage:", help_text, re.DOTALL)
    description = match_desc.group(1).strip() if match_desc else ""
    # Remove "Available categories:" from description to avoid duplication
    description = re.sub(r"Available categories:.*", "", description, flags=re.DOTALL).strip()
    # Join lines that look like they were wrapped (no space after newline, or ending in / -)
    description = re.sub(r"([/-])\n\s*", r"\1", description)
    description = re.sub(r"(\w)\n\s*(\w)", r"\1\2", description)
    # Flatten everything else to a single paragraph for now
    return re.sub(r"\s+", " ", description)


def extract_usage_and_aliases(help_text):
    match_usage = re.search(r"Usage: (.*?)\n\n", help_text, re.DOTALL)
    usage = match_usage.group(1).strip() if match_usage else ""
    # Flatten usage (remove newlines) for horizontal scrollbar
    usage = re.sub(r"\s+", " ", usage)

    match_aliases = re.search(r"Aliases: (.*?)\n\n", help_text, re.DOTALL)
    aliases = match_aliases.group(1).strip() if match_aliases else "No aliases"
    return usage, aliases


def get_demo_section(cmd):
    # Move Demo GIF to the top
    gif_path = f"../static/gifs/{cmd}.gif"
    if os.path.exists(f"docs/static/gifs/{cmd}.gif"):
        return f"![{cmd} demo]({gif_path})\n\n"
    return ""


def get_setup_categories(help_text):
    cat_match = re.search(r"Available categories:(.*?)\n\nUsage:", help_text, re.DOTALL)
    if not cat_match:
        return ""

    md = "\n### Available Categories\n\n"
    cat_text = cat_match.group(1)
    # Join wrapped words/URLs in categories too
    cat_text = re.sub(r"([/-])\n\s*", r"\1", cat_text)
    cat_text = re.sub(r"(\w)\n\s*(\w)", r"\1\2", cat_text)
    # Clean up categories text
    cat_lines = [line.rstrip() for line in cat_text.split("\n") if line.strip()]
    md += "\n".join(cat_lines) + "\n"
    return md


def parse_arguments(section_content):
    md = ""
    arg_lines = section_content.split("\n")
    current_arg = None
    current_desc = []

    for line in arg_lines:
        if not line.strip():
            continue

        # Match new argument: starts with at least 4 spaces, then the arg name, then at least 2 spaces
        match = re.match(r"^\s{4,}(--?[\w-]+(?:, --?[\w-]+)*|[\w-]+)\s{2,}(.*)", line)
        if not match:
            # Catch cases with less indentation but clearly a new flag
            match = re.match(r"^\s+(-[a-zA-Z0-9]\b|--[a-z0-9-]+)\s+(.*)", line)

        if match:
            if current_arg:
                full_desc = " ".join(current_desc).strip()
                arg_parts = [f"`{p.strip()}`" for p in current_arg.split(",")]
                md += f"| <nobr>{', '.join(arg_parts)}</nobr> | {full_desc} |\n"
            current_arg = match.group(1).strip()
            current_desc = [match.group(2).strip()]
        elif current_arg:
            # It's a continuation of the previous description
            current_desc.append(line.strip())

    if current_arg:
        full_desc = " ".join(current_desc).strip()
        arg_parts = [f"`{p.strip()}`" for p in current_arg.split(",")]
        md += f"| <nobr>{', '.join(arg_parts)}</nobr> | {full_desc} |\n"

    return md


def process_cmd(cmd, help_text):
    description = clean_description(help_text)
    usage, aliases = extract_usage_and_aliases(help_text)
    demo_section = get_demo_section(cmd)

    md = f"# odev {cmd}\n\n{demo_section}{description}\n\n## Usage\n\n```bash\n{usage}\n```\n\n### Aliases\n{aliases}\n\n## Arguments\n"

    # Parse sections
    sections = re.split(r"\n\s*(\w+ Arguments:)\n", help_text)

    # Extract "Available categories" for setup
    if cmd == "setup":
        md += get_setup_categories(help_text)

    for i in range(1, len(sections), 2):
        section_title = sections[i]
        section_content = sections[i + 1]
        md += f"\n### {section_title}\n\n| Argument | Description |\n| --- | --- |\n"
        md += parse_arguments(section_content)

    md += f"\n## Examples\n\n```bash\n# Show help\nodev {cmd} --help\n"
    if "database" in usage:
        md += f"\n# Basic usage\nodev {cmd} demo_19\n"
    if cmd == "setup":
        md += f"\n# Run specific setup category\nodev {cmd} completion\n"
    md += "```\n"

    return md


with open("scratch/odev_help_all.txt") as f:
    raw_help = f.read()

commands = {}
current_cmd = None
current_content = []

for line in raw_help.split("\n"):
    if line.startswith("--- HELP FOR "):
        if current_cmd:
            commands[current_cmd] = "\n".join(current_content)
        current_cmd = line.replace("--- HELP FOR ", "").replace(" ---", "").strip()
        current_content = []
    else:
        current_content.append(line)
if current_cmd:
    commands[current_cmd] = "\n".join(current_content)

os.makedirs("docs/commands", exist_ok=True)

CORE_COMMANDS = {
    "assets",
    "cloc",
    "clone",
    "config",
    "create",
    "delete",
    "deploy",
    "dump",
    "fetch",
    "help",
    "history",
    "info",
    "kill",
    "list",
    "neutralize",
    "pathfinder",
    "plugin",
    "pull",
    "quickstart",
    "rename",
    "restore",
    "run",
    "setup",
    "shell",
    "standardize",
    "test",
    "update",
    "upgrade-code",
    "venv",
    "version",
    "worktree",
}

for cmd, help_text in commands.items():
    if cmd not in CORE_COMMANDS:
        continue
    if not help_text.strip():
        continue
    logger.info(f"Generating docs/commands/{cmd}.md...")
    md = process_cmd(cmd, help_text)
    with open(f"docs/commands/{cmd}.md", "w") as f:
        f.write(md)
