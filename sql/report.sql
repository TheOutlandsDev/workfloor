-- Parameters are bound by sqlite3, never inserted into SQL text.
-- Due dates use [start_utc, end_utc); completions must be before end_utc.
-- Group events BEFORE joining: one source event, then one order.
WITH event_groups AS (
    SELECT order_id, source_event_id,
           MIN(occurred_at) AS occurred_at,
           COUNT(*) AS raw_rows,
           COUNT(DISTINCT COALESCE(occurred_at, '<missing>')) AS variants
    FROM completion_events
    GROUP BY order_id, source_event_id
), order_evidence AS (
    SELECT order_id,
           MIN(CASE WHEN variants = 1 AND occurred_at < :end_utc
                    THEN occurred_at END) AS completed_at,
           MAX(CASE WHEN variants > 1 THEN 1 ELSE 0 END) AS has_conflict,
           MAX(CASE WHEN occurred_at IS NULL THEN 1 ELSE 0 END) AS has_missing_time,
           SUM(CASE WHEN variants = 1 THEN raw_rows - 1 ELSE 0 END) AS replay_rows
    FROM event_groups
    GROUP BY order_id
), step_counts AS (
    SELECT order_id, COUNT(*) AS step_count
    FROM process_steps GROUP BY order_id
)
SELECT w.order_id, w.product, w.work_center, w.quantity, w.due_at,
       e.completed_at, COALESCE(s.step_count, 0) AS step_count,
       COALESCE(e.replay_rows, 0) AS replay_rows,
       CASE
           WHEN e.has_conflict = 1 THEN 'review_conflict'
           WHEN e.has_missing_time = 1 THEN 'review_missing_time'
           WHEN e.completed_at IS NULL THEN 'open_overdue'
           WHEN e.completed_at > w.due_at THEN 'completed_late'
           ELSE 'on_time'
       END AS status
FROM work_orders AS w
LEFT JOIN order_evidence AS e ON e.order_id = w.order_id
LEFT JOIN step_counts AS s ON s.order_id = w.order_id
WHERE w.due_at >= :start_utc AND w.due_at < :end_utc
ORDER BY w.due_at, w.order_id;
