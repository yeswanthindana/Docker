import os

def cleanup_temp_files(*paths):
    """Helper functional to remove temporary generated files."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
