"""Page widgets displayed in the central stack of the shell."""

from .base import PageBase
from .library import LibraryPage
from .placeholders import PlaceholderPage, RunPlaceholderPage
from .profiles import ProfilesPage

__all__ = [
    "PageBase",
    "LibraryPage",
    "PlaceholderPage",
    "ProfilesPage",
    "RunPlaceholderPage",
]
