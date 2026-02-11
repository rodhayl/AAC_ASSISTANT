import sqlite3
import os
import sys

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else r"dist\AAC_Assistant_Package\data\aac_assistant.db"

print(f"Inspecting database: {DB_PATH}")

if not os.path.exists(DB_PATH):
    print("Database file does not exist!")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

try:
    tables = ["users", "symbols", "achievements", "user_achievements", "communication_boards", "board_symbols"]
    for table in tables:
        try:
            cursor.execute(f"SELECT count(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"Table '{table}': {count} rows")
            
            if count > 0 and table == "users":
                cursor.execute("SELECT id, username, user_type FROM users")
                print("Users:", cursor.fetchall())
                
        except sqlite3.OperationalError as e:
            print(f"Table '{table}' error: {e}")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
