"""Use the same persistence implementation as the embedded backend."""
import sys
from . import paths

sys.path.insert(0, str(paths.bot_source_dir() / "src"))
from durable_files import atomic_write, config_lock, commit_files, revision
