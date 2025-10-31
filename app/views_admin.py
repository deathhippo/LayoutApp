import sqlite3
from flask import (
    Blueprint, jsonify, request, session, current_app
)
from werkzeug.security import generate_password_hash
from .auth import admin_required
from .db import get_db_connection

# All routes here will be prefixed with /api/admin
bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@bp.route('/users', methods=['GET'])
@admin_required
def get_all_users():
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        users = [dict(row) for row in conn.execute("SELECT id, username, role FROM users ORDER BY username")]
        return jsonify(users)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/users', methods=['POST'])
@admin_required
def create_new_user():
    data = request.json
    username, password, role = data.get('username'), data.get('password'), data.get('role')
    
    if not all([username, password, role]):
        return jsonify({"status": "error", "message": "Missing data"}), 400
    if role not in ['admin', 'viewer']:
        return jsonify({"status": "error", "message": "Invalid role"}), 400
    
    password_hash = generate_password_hash(password)
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     (username, password_hash, role))
        conn.commit()
        return jsonify({"status": "success", "message": f"User {username} created."})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Username already exists"}), 409
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    data = request.json
    role, password = data.get('role'), data.get('password')
    
    if not role or role not in ['admin', 'viewer']:
        return jsonify({"status": "error", "message": "Invalid role"}), 400
    
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        
        if password:
            password_hash = generate_password_hash(password)
            conn.execute("UPDATE users SET role = ?, password_hash = ? WHERE id = ?",
                         (role, password_hash, user_id))
        else:
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        
        conn.commit()
        return jsonify({"status": "success", "message": "User updated."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        
        check = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
        if check and check['username'] == session['username']:
            return jsonify({"status": "error", "message": "Cannot delete yourself"}), 403
        
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        
        if cursor.rowcount > 0:
            return jsonify({"status": "success", "message": "User deleted."})
        else:
            return jsonify({"status": "error", "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()