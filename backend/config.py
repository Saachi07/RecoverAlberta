"""Application configuration loaded from environment variables.

Persistence is delegated to Supabase. Two keys are needed server-side:

* ``SUPABASE_ANON_KEY``, used for sign-up / sign-in / password reset and for
  per-user calls where we want RLS to apply (we attach the user's access
  token to the client before each call).
* ``SUPABASE_SERVICE_ROLE_KEY``, used for server-side maintenance work that
  must bypass RLS (e.g. writing into shared catalog tables). Never expose
  this to a browser.

``SUPABASE_JWT_SECRET`` lets us verify user access tokens locally without a
round-trip to Supabase on every request.
"""

from __future__ import annotations

import os


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    # Browser origins allowed to call this API. A wildcard with credentials is
    # unsafe, so we pin known origins. Defaults cover local Vite dev; set
    # CORS_ORIGINS (comma-separated) in production to your deployed frontend,
    # e.g. "https://<user>.github.io".
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if o.strip()
    ]


class TestConfig(Config):
    TESTING = True
