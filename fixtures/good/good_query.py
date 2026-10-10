# -*- coding: utf-8 -*-
"""正面示例：合规取数代码（冒烟测试用）。"""
import os

import pymysql

conn = pymysql.connect(
    host=os.environ["DB_HOST"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
)
cursor = conn.cursor()

# 参数化查询：变量只当参数传，不进 SQL 文本
sql = "SELECT id, amount FROM orders WHERE status = %s ORDER BY created_at DESC LIMIT 100"
cursor.execute(sql, ("paid",))
rows = cursor.fetchall()
for row in rows:
    _id, _amount = row
