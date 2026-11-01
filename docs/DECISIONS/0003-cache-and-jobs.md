# Caches and job ownership

Evidence caches use TTL, stale-while-revalidate, original fetch times, bounded stale retention and coalesced requests. A backtest summary has a separate database lifetime. Owner/expiry leases deduplicate expensive jobs across workers sharing the database. A source cache is not a historical forecast archive; fixed-lead forecasts come from Previous Runs. Process-local counters and caches are not distributed state.
