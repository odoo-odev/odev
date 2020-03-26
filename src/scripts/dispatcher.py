# -*- coding: utf-8 -*-

from . import clean
from . import create
from . import listing
from . import remove
from . import rename
from . import restore
from . import run
from . import version

dispatcher = {
    'clean': clean.CleanScript(),
    'create': create.CreateScript(),
    'listing': listing.ListingScript(),
    'remove': remove.RemoveScript(),
    'rename': rename.RenameScript(),
    'restore': restore.RestoreScript(),
    'run': run.RunScript(),
    'version': version.VersionScript(),
}
