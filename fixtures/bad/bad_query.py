# -*- coding: utf-8 -*-
"""反面教材：问题取数代码（冒烟测试用，不要模仿）。"""
import pymysql

conn = pymysql.connect(host="127.0.0.1", user="root", password="root123456")
cursor = conn.cursor()

# SQL 拼接：f-string 把变量拼进 SQL（注入风险）
name = "o'brien"
sql = f"SELECT * FROM users WHERE name = '{name}'"
cursor.execute(sql)

# SQL 拼接：字符串相加
order_id = "42"
sql2 = "SELECT * FROM orders WHERE id = " + order_id
cursor.execute(sql2)

# N+1：循环里逐条查
ids = [1, 2, 3]
for user_id in ids:
    cursor.execute("SELECT name FROM users WHERE id = %s", (user_id,))
    print(cursor.fetchone())
