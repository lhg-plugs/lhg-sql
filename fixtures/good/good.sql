-- 正面示例：合规取数 SQL（冒烟测试用）。方言：MySQL。
-- 取数：近 7 天已支付订单（带用户名）
SELECT o.id, o.amount, u.name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'paid'
  AND o.created_at >= '2026-10-04'
ORDER BY o.created_at DESC
LIMIT 100;

-- 更新：带 WHERE，只改一行
UPDATE orders SET status = 'shipped' WHERE id = 123;

-- 写入：显式列名
INSERT INTO export_log (job, rows_n) VALUES ('daily', 100);
