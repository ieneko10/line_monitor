import sqlite3

# ファイルベースのデータベースに接続（sample.db がない場合は自動生成される）
conn = sqlite3.connect("sample.db")

# ※ メモリ上のDBを利用する場合は以下のようにします
# conn = sqlite3.connect(":memory:")

# カーソルを作成
cursor = conn.cursor()

# users というテーブルを作成（存在しなければ実行される）
create_table_query = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    age INTEGER,
    time INTEGER
);
"""
cursor.execute(create_table_query)

# テーブル作成は書き込み操作なので、コミットが必要です
conn.commit()

# 単一レコードの挿入(重複なし)
insert_query = "INSERT OR IGNORE INTO users (name, age) VALUES (?, ?)"
cursor.execute(insert_query, ("Alice", None))

# 単一レコードの挿入(重複なし)
insert_query = "INSERT OR IGNORE INTO users (time) VALUES (?)"
cursor.execute(insert_query, (0,))

# 複数レコードの挿入
data_to_insert = [
    ("Bob", 25),
    ("Charlie", 35),
    ("David", 28)
]
cursor.executemany(insert_query, data_to_insert)

# 挿入した変更を反映するためにコミットする
conn.commit()

# 全てのユーザーデータを取得する
select_query = "SELECT id, name, age FROM users"
cursor.execute(select_query)

# 結果を全件取得する
rows = cursor.fetchall()
print("----- 全ユーザーデータ -----")
for row in rows:
    print(f"ID: {row[0]}, Name: {row[1]}, Age: {row[2]}")
print("")

# 年齢が 25 のユーザーの名前を "Bobby" に更新する
update_query = """
INSERT INTO users (name, age)
VALUES (?, ?)
ON CONFLICT(name) DO UPDATE SET age = excluded.age;
"""
cursor.execute(update_query, ("Bobby", 25))
conn.commit()

# 更新後のデータを再度取得して表示
cursor.execute(select_query)
rows = cursor.fetchall()
print("----- 年齢が 25 のユーザーの名前を更新後のデータ -----")
for row in rows:
    print(f"ID: {row[0]}, Name: {row[1]}, Age: {row[2]}")
print("")
    
# 年齢が 35 のユーザーを削除する
delete_query = "DELETE FROM users WHERE age = ?"
cursor.execute(delete_query, (35,))
conn.commit()

# 削除後のデータを再度取得して表示
cursor.execute(select_query)
rows = cursor.fetchall()
print("----- 年齢が 35 のユーザーを削除後のデータ -----")
for row in rows:
    print(f"ID: {row[0]}, Name: {row[1]}, Age: {row[2]}")
print("-----")

# カーソルと接続を閉じる
cursor.close()
conn.close()
