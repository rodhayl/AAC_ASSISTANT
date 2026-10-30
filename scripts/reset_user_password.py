import os
import sqlite3
import sys
import bcrypt

def reset_password(username, new_password):
    db_path = os.path.join("data", "aac_assistant.db")
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Passlib might be having issues with python 3.13 / bcrypt version mismatch
    # Let's use raw bcrypt
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (hashed, username))
    if cursor.rowcount == 0:
        print(f"User {username} not found.")
    else:
        print(f"Password for {username} updated successfully.")
        conn.commit()
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python reset_user_password.py <username> <password>")
    else:
        reset_password(sys.argv[1], sys.argv[2])
