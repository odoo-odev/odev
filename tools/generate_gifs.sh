#!/bin/bash

# ==============================================================================
# ODEV documentation GIF generator
# Automates the creation of standard GIFs for documentation.
# ==============================================================================

set -e

# Resolve paths
TOOLS_DIR=$(cd $(dirname $0) && pwd)
REPO_ROOT=$(cd $TOOLS_DIR/.. && pwd)
RECORD_SH=$TOOLS_DIR/record.sh

# Ensure we run from the repository root
cd "$REPO_ROOT"

echo "::: Cleaning up existing odoo-bin processes for demo databases..."
pkill -9 -f "odoo-bin.*(-d|--database) demo" || true
sleep 2

echo "::: Cleaning up existing databases..."
# -w: include whitelisted, -e .*: match all, -f: force (bypass prompt), -H: headless
psql -d odev -c "UPDATE databases SET whitelisted=False WHERE name like 'demo_%'"
odev delete -f -e "demo_*" || true

echo "::: Cleaning up history..."
odev history --clear -f

echo "::: Cleaning up venv..."
odev venv --remove 17.0 || true

# ------------------------------------------------------------------------------
# odev create
# Creates new Odoo databases with specific versions and configurations.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev create'..."
# Simple: basic creation
$RECORD_SH "odev create -V 19.0 demo_19" 15 140 create_simple
# Complex: forced creation with community version and no demo data
$RECORD_SH "odev create -f -V 18.0 demo_18 --community --without-demo" 18 140 create_advanced

echo "::: Whitelisting demo_19..."
psql -d odev -c "UPDATE databases SET whitelisted=True WHERE name='demo_19'"

# ------------------------------------------------------------------------------
# odev list
# Lists available Odoo databases and their metadata.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev list'..."
# Simple: basic list
$RECORD_SH "odev list" 10 140 list_simple
# Complex: list all databases with detailed version information
$RECORD_SH "odev list -a -v" 14 140 list_advanced

# ------------------------------------------------------------------------------
# odev fetch & pull
# Manage Odoo source code updates from remotes.
# ------------------------------------------------------------------------------
echo "::: Preparing for fetch/pull..."
# Move remote-tracking branches back so fetch has something to download
git -C /home/crupuk/odev/worktrees/19.0/odoo update-ref refs/remotes/origin/19.0 refs/remotes/origin/19.0~5
git -C /home/crupuk/odev/worktrees/19.0/enterprise update-ref refs/remotes/origin/19.0 refs/remotes/origin/19.0~5
# Local branches Behind the remote
git -C /home/crupuk/odev/worktrees/19.0/odoo reset --hard HEAD~5 > /dev/null
git -C /home/crupuk/odev/worktrees/19.0/enterprise reset --hard HEAD~5 > /dev/null

echo "::: Recording 'odev fetch'..."
$RECORD_SH "odev fetch" 20 140 fetch

echo "::: Recording 'odev pull'..."
# Reset further back to show a nice list of changes
git -C /home/crupuk/odev/worktrees/19.0/odoo reset --hard HEAD~15 > /dev/null
git -C /home/crupuk/odev/worktrees/19.0/enterprise reset --hard HEAD~15 > /dev/null
$RECORD_SH "odev pull -V 19.0" 25 140 pull

# ------------------------------------------------------------------------------
# odev rename
# Renames an existing Odoo database.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev rename'..."
$RECORD_SH "odev rename demo_18 demo_18_backup" 5 140 rename

# ------------------------------------------------------------------------------
# odev deploy
# Deploys a local module to a target database.
# ------------------------------------------------------------------------------
MODULE_PATH="/home/crupuk/odoo/repositories/odoo-odev/odev/tests/fixtures/test_module"
echo "::: Recording 'odev deploy'..."
# Simple: basic deploy
$RECORD_SH "odev deploy demo_19 ${MODULE_PATH}" 10 140 deploy_simple --fast
# Complex: deploy with force update and no data update
$RECORD_SH "odev deploy demo_19 ${MODULE_PATH} --force --no-update" 12 140 deploy_advanced --fast

# ------------------------------------------------------------------------------
# odev run
# Starts the Odoo server for a specific database.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev run'..."
# Simple: basic run with auto-stop after init
$RECORD_SH "odev run demo_19 --stop-after-init" 25 140 run_simple
# Complex: run with module installation and update
$RECORD_SH "odev run demo_19 -i sale_management -u base --stop-after-init" 30 140 run_advanced

# ------------------------------------------------------------------------------
# odev config
# Manages odev CLI configuration.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev config'..."
$RECORD_SH "odev config" 20 140 config --cut

# ------------------------------------------------------------------------------
# odev history
# Displays the history of executed odev commands.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev history'..."
$RECORD_SH "odev history" 15 140 history

# ------------------------------------------------------------------------------
# odev dump & restore
# Backup and restore Odoo databases.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev dump'..."
rm -f /home/crupuk/odoo/dumps/*-demo_19.dump*
$RECORD_SH "odev dump -F demo_19" 10 140 dump

echo "::: Recording 'odev restore'..."
DUMP_FILE="/home/crupuk/odoo/dumps/odev.dump.zip"
if [ -f "$DUMP_FILE" ]; then
    $RECORD_SH "odev restore demo_restored -f $DUMP_FILE" 15 140 restore
fi

# ------------------------------------------------------------------------------
# odev test
# Runs Odoo tests for a specific database and module.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev test'..."
# Simple: run tests for a specific tag
$RECORD_SH "odev test demo_19 --test-tags .test_sale_ui" 15 140 test_simple
# Complex: run tests with AI assistance and verbose output
$RECORD_SH "odev test demo_19 -i sale_management --ai" 20 140 test_advanced

# ------------------------------------------------------------------------------
# odev upgrade-code
# Upgrades module code (XML/Python) to a newer Odoo version.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev upgrade-code'..."
# Prepare dummy module for upgrade
mkdir -p /tmp/demo_17/presales
echo "{'name': 'Presales', 'version': '17.0.1.0.0', 'depends': ['base'], 'data': ['view.xml']}" > /tmp/demo_17/presales/__manifest__.py
echo '<odoo><record id="view_presales_tree" model="ir.ui.view"><field name="name">p.tree</field><field name="model">res.partner</field><field name="arch" type="xml"><tree><field name="name"/></tree></field></record></odoo>' > /tmp/demo_17/presales/view.xml
odev create -f -V 17.0 demo_17_db > /dev/null 2>&1
odev run demo_17_db -i presales --addons /tmp/demo_17 --stop-after-init > /dev/null 2>&1

$RECORD_SH 'odev upgrade-code --from 17 --to 19.0 demo_17_db --glob="/tmp/demo_17/presales/**/*"' 20 140 upgrade_code
rm -rf /tmp/demo_17
odev delete -f demo_17_db > /dev/null 2>&1

# ------------------------------------------------------------------------------
# odev version
# Displays the version of odev and linked Odoo versions.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev version'..."
$RECORD_SH "odev version" 5 140 version

# ------------------------------------------------------------------------------
# odev cloc
# Counts lines of code in Odoo modules, excluding standard Odoo code.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev cloc'..."
$RECORD_SH "odev cloc demo_19" 12 140 cloc

# ------------------------------------------------------------------------------
# odev kill
# Kills Odoo processes for a specific database.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev kill'..."
$RECORD_SH "odev kill demo_19" 5 140 kill

# ------------------------------------------------------------------------------
# odev venv
# Manages virtual environments for different Odoo versions.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev venv'..."
# Simple: list environments
$RECORD_SH "odev venv --list" 10 140 venv_list
# Complex: check a specific version
$RECORD_SH "odev venv --check 19.0" 12 140 venv_check

# ------------------------------------------------------------------------------
# odev neutralize
# Neutralizes an Odoo database (disables crons, emails, etc.).
# ------------------------------------------------------------------------------
echo "::: Recording 'odev neutralize'..."
$RECORD_SH "odev neutralize demo_19" 20 140 neutralize

# ------------------------------------------------------------------------------
# odev delete
# Deletes Odoo databases and their associated metadata.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev delete'..."
odev create -f -V 19.0 demo_to_delete > /dev/null 2>&1
$RECORD_SH "odev delete -f demo_to_delete" 6 140 delete

# ------------------------------------------------------------------------------
# odev pathfinder
# Finds technical paths between Odoo models (relation fields).
# ------------------------------------------------------------------------------
echo "::: Recording 'odev pathfinder'..."
odev run demo_19 -i sale_management,purchase --stop-after-init > /dev/null 2>&1
$RECORD_SH "odev pathfinder demo_19 sale.order.line account.move.line" 25 140 pathfinder

# ------------------------------------------------------------------------------
# odev update
# Updates Odoo modules in a database.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev update'..."
# Simple: update a specific module
$RECORD_SH "odev update demo_19 -u sale_management" 10 140 update_simple
# Complex: update all modules
$RECORD_SH "odev update demo_19 -a" 15 140 update_all

# ------------------------------------------------------------------------------
# odev clone
# Clones Odoo repositories and registers them in odev.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev clone'..."
rm -rf /home/crupuk/odoo/repositories/odoo-ps/custom-utils
$RECORD_SH "odev clone odoo-ps/custom-utils" 8 140 clone

# ------------------------------------------------------------------------------
# odev worktree
# Manages Odoo version-specific worktrees.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev worktree'..."
$RECORD_SH "odev worktree --list" 15 140 worktree

# ------------------------------------------------------------------------------
# odev standardize
# Standardizes module structure and manifest files.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev standardize'..."
$RECORD_SH "odev standardize demo_19" 10 140 standardize

# ------------------------------------------------------------------------------
# odev shell
# Opens an interactive Odoo shell or runs a script.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev shell'..."
$RECORD_SH "odev shell demo_19 --script 'print(env[\"res.users\"].search([], limit=1).name) and exit(0)'" 12 140 shell

# ------------------------------------------------------------------------------
# odev plugin
# Manages odev CLI plugins.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev plugin'..."
odev plugin --disable odoo-odev/odev-plugin-ai || true
$RECORD_SH "odev plugin --enable odoo-odev/odev-plugin-ai" 12 140 plugin

# ------------------------------------------------------------------------------
# odev info
# Displays detailed information about an Odoo database.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev info'..."
$RECORD_SH "odev info demo_19" 12 140 info

# ------------------------------------------------------------------------------
# odev help
# Displays help information for odev commands.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev help'..."
$RECORD_SH "odev help" 25 140 help

# ------------------------------------------------------------------------------
# odev assets
# Manages and regenerates Odoo web assets.
# ------------------------------------------------------------------------------
echo "::: Preparing 'website' and assets for demo_19..."
odev run demo_19 -i website --stop-after-init > /dev/null 2>&1
odev run demo_19 > /dev/null 2>&1 &
RUN_PID=$!
sleep 10
wget -q -O /dev/null http://localhost:8069 || true
kill $RUN_PID || true
sleep 2

echo "::: Recording 'odev assets'..."
$RECORD_SH "odev assets demo_19" 14 140 assets

# ------------------------------------------------------------------------------
# odev setup
# Initial setup and configuration of the odev environment.
# ------------------------------------------------------------------------------
echo "::: Recording 'odev setup'..."
# Simulation script handles interactive prompts
"$RECORD_SH" "python3 $TOOLS_DIR/simulate_setup.py" 20 140 setup
mv "$REPO_ROOT/docs/static/gifs/python3.gif" "$REPO_ROOT/docs/static/gifs/setup.gif" || true

echo "::: All GIFs generated successfully in docs/static/gifs/"
