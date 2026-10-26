-- INTENTIONALLY INCORRECT: COUNT(*) counts joined rows, not work orders.
-- A planned step and a raw completion row are both one-to-many relationships.
-- Joining both directly multiplies their rows, including replayed events.
SELECT COUNT(*) AS work_order_count, COALESCE(SUM(w.quantity), 0) AS units
FROM work_orders AS w
LEFT JOIN process_steps AS s ON s.order_id = w.order_id
LEFT JOIN completion_events AS e
       ON e.order_id = w.order_id
      AND (e.occurred_at < :end_utc OR e.occurred_at IS NULL)
WHERE w.due_at >= :start_utc AND w.due_at < :end_utc;
