-- Read-only PostgreSQL client refresh report. No payload, credentials or private notes.
-- Legacy synthetic filament IDs were spool IDs, not material identifiers.
SELECT
    r.user_id AS account_id,
    CAST(r.original_payload -> 'legacy_spool' ->> 'id' AS INTEGER) AS spool_id,
    CAST(r.original_payload -> 'legacy_spool' ->> 'id' AS INTEGER) AS previous_filament_id,
    r.wire_id AS migrated_filament_id,
    s.compat_filament_ref_id = r.id AS still_uses_migrated_reference
FROM spool_compat_resources AS r
LEFT JOIN user_spools AS s
    ON s.id = CAST(r.original_payload -> 'legacy_spool' ->> 'id' AS INTEGER)
    AND s.user_id = r.user_id
WHERE r.kind = 'filament'
    AND r.source_kind = 'import'
    AND r.original_payload -> 'legacy_spool' ->> 'id' IS NOT NULL
ORDER BY r.user_id, spool_id;
