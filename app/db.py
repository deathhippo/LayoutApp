import sqlite3
import os
from flask import current_app, g

def get_db_connection(db_file_path):
    """Establishes a connection to the specified SQLite database."""
    if not os.path.exists(db_file_path):
        print(f"ERROR: Database file not found at '{db_file_path}'.")
        if db_file_path == current_app.config['CAS_DATABASE_FILE_PATH']:
            print(f"Warning: '{os.path.basename(db_file_path)}' not found. Worker names cannot be fetched.")
            return None
        raise FileNotFoundError(f"Database file not found at '{db_file_path}'.")
    try:
        conn = sqlite3.connect(db_file_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        print(f"ERROR: Could not connect to database '{db_file_path}': {e}")
        if db_file_path == current_app.config['CAS_DATABASE_FILE_PATH']:
            print(f"Warning: Could not connect. Worker names cannot be fetched.")
            return None
        raise e

def init_velika_montaza_db():
    """Initializes the schema for the velika_montaza database if tables don't exist."""
    conn = None
    try:
        # Use the config path
        db_path = current_app.config['VELIKA_MONTAZA_DB_PATH']
        conn = get_db_connection(db_path)
        if conn is None:
            print(f"ERROR: Cannot initialize '{os.path.basename(db_path)}' as it could not be connected to.")
            return

        cursor = conn.cursor()
        # Project notes and statuses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_notes (
                project_task_no TEXT PRIMARY KEY,
                notes TEXT,
                electrification_notes TEXT,
                control_notes TEXT,
                electrification_status TEXT,
                control_status TEXT,
                electrification_completed_at TEXT,
                control_completed_at TEXT,
                packaging_status TEXT,
                priority TEXT,
                pause_status TEXT,
                last_note_updated_at TEXT,
                last_dni_updated_at TEXT
            )""")
        
        # Add columns if they don't exist (for older DBs)
        try: cursor.execute("SELECT priority FROM project_notes LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding 'priority' column to project_notes table.")
            cursor.execute("ALTER TABLE project_notes ADD COLUMN priority TEXT")
        
        try: cursor.execute("SELECT pause_status FROM project_notes LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding 'pause_status' column to project_notes table.")
            cursor.execute("ALTER TABLE project_notes ADD COLUMN pause_status TEXT")
        
        try: cursor.execute("SELECT last_note_updated_at FROM project_notes LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding 'last_note_updated_at' column to project_notes table.")
            cursor.execute("ALTER TABLE project_notes ADD COLUMN last_note_updated_at TEXT")

        try: cursor.execute("SELECT last_dni_updated_at FROM project_notes LIMIT 1")
        except sqlite3.OperationalError:
            print("Adding 'last_dni_updated_at' column to project_notes table.")
            cursor.execute("ALTER TABLE project_notes ADD COLUMN last_dni_updated_at TEXT")

        # DNI status table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dni_status (
                work_order_no TEXT PRIMARY KEY,
                project_task_no TEXT NOT NULL,
                description TEXT,
                is_completed BOOLEAN NOT NULL CHECK (is_completed IN (0, 1))
            )""")
        # Project photos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_task_no TEXT NOT NULL,
                filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
        """)
        # User table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'viewer'))
            )""")

        conn.commit()
        print("Velika Montaza database schema is verified.")
    except sqlite3.OperationalError as e:
        print(f"ERROR initializing Velika Montaza database: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during Velika Montaza DB initialization: {e}")
    finally:
        if conn:
            conn.close()

# This function registers the init function with the Flask app
def init_app(app):
    # You can add a CLI command here if you want, e.g., "flask init-db"
    # For simplicity, we'll just call init_velika_montaza_db from run.py
    pass