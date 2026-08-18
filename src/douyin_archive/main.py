from .api import create_app
from .config import Settings
from .runtime import ArchiveRuntime

settings = Settings()
app = create_app(settings, runtime_factory=ArchiveRuntime)
