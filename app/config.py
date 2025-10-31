import os

# --- CONFIGURATION ---
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # Points to /your_project_folder

DATABASE_FILE = 'projekti_baza.db'
VELIKA_MONTAZA_DB_FILE = 'velika_montaza.db'
CAS_DATABASE_FILE = 'cas_baza.db'
LAYOUT_DATA_FILE = 'layout_data.json'

# --- Full Paths (Cleaner) ---
DATABASE_FILE_PATH = os.path.join(APP_ROOT, DATABASE_FILE)
VELIKA_MONTAZA_DB_PATH = os.path.join(APP_ROOT, VELIKA_MONTAZA_DB_FILE)
CAS_DATABASE_FILE_PATH = os.path.join(APP_ROOT, CAS_DATABASE_FILE)
LAYOUT_DATA_FILE_PATH = os.path.join(APP_ROOT, LAYOUT_DATA_FILE)
UPLOADS_FOLDER = os.path.join(APP_ROOT, 'uploads')

# --- App Settings ---
SECRET_KEY = 'your_super_secret_key_change_me' # IMPORTANT: Change this!
UPRAVLJALNI_CENTER_SKLOP = '303'