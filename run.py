from waitress import serve
from app import create_app
import os
import json

app = create_app()

if __name__ == '__main__':
    # Startup checks (moved from the bottom of the old file)
    os.makedirs(app.config['UPLOADS_FOLDER'], exist_ok=True)

    essential_dbs = [
        app.config['DATABASE_FILE_PATH'], 
        app.config['VELIKA_MONTAZA_DB_PATH'], 
        app.config['CAS_DATABASE_FILE_PATH']
    ]
    missing_dbs = [db for db in essential_dbs if not os.path.exists(db)]
    
    if missing_dbs:
        print("\n--- !! WARNING !! ---")
        for db_path in missing_dbs:
            print(f"Essential database file '{os.path.basename(db_path)}' is missing at '{db_path}'.")
        print("---------------------\n")
        if app.config['CAS_DATABASE_FILE_PATH'] in missing_dbs:
             print("--- NOTE: Automatic worker assignment requires 'cas_baza.db'. ---\n")

    layout_path = app.config['LAYOUT_DATA_FILE_PATH']
    if not os.path.exists(layout_path):
        print(f"\n--- WARNING: Layout file '{os.path.basename(layout_path)}' not found. Creating a new empty file. ---\n")
        try:
            with open(layout_path, 'w', encoding='utf-8') as f:
                json.dump({"items": [], "background": {}}, f, indent=4)
        except Exception as e:
            print(f"ERROR: Could not create '{layout_path}': {e}")
    
    # Call the DB init command registered in db.py
    with app.app_context():
        from app.db import init_velika_montaza_db
        init_velika_montaza_db() # Run the init check

    print("\n--- Factory Layout Server is Running with Waitress ---")
    print(f"Access the main app at: http://127.0.0.1:5005")
    print(f"Access the planning view at: http://127.0.0.1:5005/planning")
    print(f"Access the admin panel at: http://127.0.0.1:5005/admin")

    serve(app, host='0.0.0.0', port=5005, threads=8)