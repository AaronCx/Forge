"""Legacy database module — bridges to the new pluggable app.db layer.

All new code should use:
    from app.db import get_db
    db = get_db()

This module exists only for backward compatibility during migration.
"""

import os

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Only create the raw supabase client if credentials are available.
# During the migration, files that still import `from app.database import supabase`
# will get the raw client. Files migrated to `from app.db import get_db` use the
# pluggable backend.
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    from supabase import Client, create_client

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
else:
    # SQLite mode — no supabase client needed. Files using this import
    # should be migrated to use app.db.get_db() instead.
    supabase = None  # type: ignore[assignment]
