import os
import sqlite3
import sys

def clear_lockout(username):
    db_path = os.path.join("data", "aac_assistant.db")
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # In this system, lockout logic is likely tracked via the failed_login_attempts table (audit logs) 
    # or a separate table if the columns don't exist on users.
    # Based on audit_log.py, there is FailedLoginAttempt model/table.
    # Let's check the schema of failed_login_attempts table first
    # But simpler is to just delete recent failed attempts for this user
    
    try:
        cursor.execute("DELETE FROM failed_login_attempts WHERE username = ?", (username,))
        if cursor.rowcount == 0:
             print(f"No failed attempts found for {username} to clear.")
        else:
             print(f"Cleared {cursor.rowcount} failed attempts for {username}.")
             conn.commit()
    except Exception as e:
        print(f"Error clearing attempts: {e}")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clear_user_lockout.py <username>")
    else:
        clear_lockout(sys.argv[1])
