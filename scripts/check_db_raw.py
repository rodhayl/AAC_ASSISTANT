import os
import sqlite3

db_path = os.path.join("data", "aac_assistant.db")
print(f"Checking DB at: {db_path}")

if not os.path.exists(db_path):
    print("DB file does not exist!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List boards
try:
    cursor.execute("SELECT id, name FROM communication_boards")
    boards = cursor.fetchall()
    print("Boards:")
    for board in boards:
        print(f"ID: {board[0]}, Name: {board[1]}")
except Exception as e:
    print("Error querying boards:", e)

conn.close()
