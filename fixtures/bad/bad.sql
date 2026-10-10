-- 反面教材：问题 SQL（冒烟测试用，不要模仿）。方言：MySQL。
-- 1. UPDATE 缺 WHERE：会把全表状态都改掉
UPDATE orders SET status = 'shipped';

-- 2. DELETE 缺 WHERE：清空整表
DELETE FROM temp_import;

-- 3. 破坏性操作
DROP TABLE old_backup;

-- 4. SELECT * + 无 WHERE + 无 LIMIT
SELECT * FROM users;

-- 5. 前导通配符 LIKE（索引失效）
SELECT id, name FROM users WHERE name LIKE '%张%';

-- 6. 方言误用：ILIKE 是 PostgreSQL 专有，MySQL 不支持
SELECT id, name FROM users WHERE name ILIKE '张%' LIMIT 100;

-- 7. 逗号连接多表（笛卡尔积风险）
SELECT o.id, u.name FROM orders o, users u LIMIT 100;

-- 8. WHERE 1=1 恒真条件
SELECT id FROM orders WHERE 1=1 AND status = 'paid' LIMIT 100;

-- 9. INSERT 未指定列名
INSERT INTO logs VALUES (1, 'x', NOW());

-- 10. ORDER BY 序数
SELECT id, amount FROM orders ORDER BY 1 LIMIT 100;
