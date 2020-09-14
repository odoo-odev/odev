# -*- coding: utf-8 -*-

from . import clean
from . import create
from . import dump
from . import init
from . import kill
from . import listing
from . import quickstart
from . import remove
from . import rename
from . import restore
from . import run
from . import version

dispatcher = {
    'clean': clean.CleanScript(),
    'create': create.CreateScript(),
    'dump': dump.DumpScript(),
    'init': init.InitScript(),
    'kill': kill.KillScript(),
    'list': listing.ListingScript(),
    'ls': listing.ListingScript(),
    'quickstart': quickstart.QuickStartScript(),
    'qs': quickstart.QuickStartScript(),
    'remove': remove.RemoveScript(),
    'rm': remove.RemoveScript(),
    'rename': rename.RenameScript(),
    'mv': rename.RenameScript(),
    'restore': restore.RestoreScript(),
    'run': run.RunScript(),
    'version': version.VersionScript(),
    'v': version.VersionScript(),
}
