-- Phase 1: one user + one AI role = one active office_colleague thread.
-- Existing dev data contains duplicate threads; merge their messages into a
-- canonical thread, soft-delete the duplicates, then enforce uniqueness.
BEGIN;

WITH msg_counts AS (
    SELECT
        m.thread_id,
        COUNT(*) AS total_msgs,
        COUNT(*) FILTER (WHERE m.role = 'user') AS user_msgs
    FROM opportunities.assistant_messages m
    WHERE m.deleted_at IS NULL
    GROUP BY m.thread_id
),
ranked AS (
    SELECT
        t.thread_id,
        t.created_by,
        t.colleague_role_key,
        t.title,
        COALESCE(mc.total_msgs, 0) AS total_msgs,
        COALESCE(mc.user_msgs, 0) AS user_msgs,
        t.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY t.created_by, t.colleague_role_key
            ORDER BY
                CASE WHEN t.deleted_at IS NULL THEN 0 ELSE 1 END,
                COALESCE(mc.total_msgs, 0) DESC,
                t.created_at ASC
        ) AS rn
    FROM opportunities.assistant_threads t
    LEFT JOIN msg_counts mc ON mc.thread_id = t.thread_id
    WHERE t.thread_kind = 'office_colleague'
      AND t.colleague_role_key IS NOT NULL
),
canonical AS (
    SELECT thread_id, created_by, colleague_role_key
    FROM ranked
    WHERE rn = 1
),
moved_messages AS (
    UPDATE opportunities.assistant_messages
    SET thread_id = d.canonical_thread_id
    FROM (
        SELECT c.thread_id AS canonical_thread_id,
               t.thread_id AS source_thread_id
        FROM opportunities.assistant_threads t
        JOIN canonical c
          ON c.created_by = t.created_by
         AND c.colleague_role_key = t.colleague_role_key
        WHERE t.thread_kind = 'office_colleague'
          AND t.colleague_role_key IS NOT NULL
          AND t.thread_id <> c.thread_id
    ) d
    WHERE assistant_messages.thread_id = d.source_thread_id
      AND assistant_messages.deleted_at IS NULL
      AND assistant_messages.kind <> 'opening'
),
deleted_threads AS (
    UPDATE opportunities.assistant_threads t
    SET deleted_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    FROM canonical c
    WHERE t.thread_id <> c.thread_id
      AND t.thread_kind = 'office_colleague'
      AND t.colleague_role_key = c.colleague_role_key
      AND t.created_by = c.created_by
      AND t.deleted_at IS NULL
)
SELECT 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_assistant_office_thread_active
ON opportunities.assistant_threads (created_by, colleague_role_key)
WHERE thread_kind = 'office_colleague'
  AND colleague_role_key IS NOT NULL
  AND deleted_at IS NULL;

COMMIT;
