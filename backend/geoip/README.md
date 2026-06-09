# GeoIP database

This directory holds the MaxMind-DB formatted country database used for
geo-restricting OAuth providers (RF law: Google must not be offered to users in
Russia). The file is **not** committed — provision it on the server.

The path is configured via `GEOIP_DB_PATH` (default `geoip/dbip-country-lite.mmdb`,
relative to the backend working directory). The directory is mounted read-only
into the backend container at `/app/geoip`.

## Option A — db-ip Lite (no account, CC-BY, recommended)

```bash
cd ~/FilamentHub/backend/geoip
MONTH=$(date +%Y-%m)
curl -L "https://download.db-ip.com/free/dbip-country-lite-${MONTH}.mmdb.gz" -o db.mmdb.gz
gunzip -f db.mmdb.gz
mv "db.mmdb" dbip-country-lite.mmdb
```

Refresh monthly (the dataset is published per month). A cron job is enough.

## Option B — MaxMind GeoLite2 (free account + license key)

Download `GeoLite2-Country.mmdb` via your MaxMind account or `geoipupdate`, place
it here, and point `GEOIP_DB_PATH` at it.

## Behaviour when the database is missing

If the file (or the `geoip2` library) is absent, geo lookups return "unknown" and
the `OAUTH_GEO_FALLBACK_ALLOW` setting decides the outcome:

- `true`  (default) — restricted providers stay allowed by geo; the UI language
  gate still hides Google for the Russian interface.
- `false` — restricted providers are blocked until the database is in place
  (fail-closed; safest legally).
