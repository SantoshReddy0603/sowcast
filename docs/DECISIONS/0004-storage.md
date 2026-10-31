# Storage and migrations

SQLAlchemy models and explicit Alembic revisions support SQLite/aiosqlite locally and PostgreSQL/asyncpg for hosted deployment. Initial migration adopts existing local tables without deleting rows. PostgreSQL transaction locks preserve lease ownership and bounded retention. Hosted records are kept outside the API filesystem, which free hosts may erase. Neon is the documented free database choice after comparing current official limits; no hosted instance has been provisioned.
