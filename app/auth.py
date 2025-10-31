from flask import (
    Blueprint, jsonify, request, session, redirect, url_for
)
from functools import wraps
from werkzeug.security import check_password_hash
from .db import get_db_connection
from flask import current_app # Import current_app to access config

# Create a Blueprint. All routes defined here will be registered with this.
bp = Blueprint('auth', __name__, url_prefix='/api')

# --- Decorators ---
def login_required(f):
    """Decorator to ensure user is logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # Allow access to login, planning, and planning_data without session
            if request.path.startswith('/api/login') or request.path == '/planning' or request.path == '/api/planning_data':
                return f(*args, **kwargs) # Allow access

            if request.path.startswith('/api/'): return jsonify({"error": "Authentication required"}), 401 # Other API needs login
            return redirect(url_for('core.serve_app')) # Redirect to main login (now in 'core' Blueprint)
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to ensure user is logged in AND has admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"error": "Authentication required"}), 401
        if session.get('role') != 'admin':
            return jsonify({"error": "Admin privileges required"}), 403 # 403 Forbidden for non-admins
        return f(*args, **kwargs)
    return decorated_function

# --- Auth Routes ---
@bp.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('role', None)
    print("User logged out.")
    return redirect(url_for('core.serve_app')) # Redirect to main login page

@bp.route('/login', methods=['POST'])
def web_app_login():
    """Handles user login attempts."""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    conn = None
    try:
        # Get DB path from config
        db_path = current_app.config['VELIKA_MONTAZA_DB_PATH']
        conn = get_db_connection(db_path)
        if conn is None:
            raise sqlite3.OperationalError(f"Could not connect to '{os.path.basename(db_path)}' for login.")

        user_row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

        if user_row and check_password_hash(user_row['password_hash'], password):
            session['logged_in'] = True
            session['username'] = user_row['username']
            session['role'] = user_row['role']
            print(f"Login successful for user: {username}, role: {user_row['role']}")
            return jsonify({"status": "success", "role": user_row['role'], "username": user_row['username']})

        print(f"Login failed for user: {username}")
        return jsonify({"status": "error", "message": "Invalid Credentials."}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"status": "error", "message": "Server error during login."}), 500
    finally:
        if conn:
            conn.close()