import os
import json
from flask import (
    Blueprint, jsonify, request, session, current_app
)
import sqlite3
from .auth import login_required, admin_required
from .db import get_db_connection
from .helpers import check_layout_item_ownership, get_latest_worker_from_cas_db

# All routes in this file will be prefixed with /api
bp = Blueprint('layout', __name__, url_prefix='/api')

@bp.route('/available_projects')
@login_required
def get_available_projects():
    """Gets a list of projects from the DB that are not in the layout file."""
    conn = None
    try:
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        
        all_db_projects = {row['project_task_no'] for row in conn.execute("SELECT DISTINCT project_task_no FROM work_orders")}
        
        layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
        projects_in_layout = set()
        if os.path.exists(layout_path):
            try:
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
                    projects_in_layout = {item['name'] for item in layout_data.get('items', []) if item.get('type') == 'project'}
            except (json.JSONDecodeError, FileNotFoundError):
                pass # Ignore if file is bad, just return full list
        
        available_projects = sorted(list(all_db_projects - projects_in_layout))
        return jsonify(available_projects)
    except sqlite3.OperationalError as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/add_project_to_layout', methods=['POST'])
@admin_required
def add_project_to_layout():
    """Adds a project to the layout JSON file."""
    data = request.json
    project_name = data.get('project_name')
    x, y = data.get('x'), data.get('y')
    current_user = session.get('username')

    if not all([project_name, x is not None, y is not None]):
        return jsonify({"status": "error", "message": "Missing data"}), 400
    
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        layout_data = {"items": [], "background": {}}
        if os.path.exists(layout_path):
            try:
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
            except json.JSONDecodeError:
                pass # Start with fresh data
        
        if any(item.get('name') == project_name for item in layout_data.get('items', []) if item.get('type') == 'project'):
            return jsonify({"status": "error", "message": "Project already exists in layout"}), 409

        initial_worker = get_latest_worker_from_cas_db([project_name]).get(project_name, "")
        
        new_project = {
            "type": "project", "name": project_name,
            "details": initial_worker, "image_path": None,
            "pinned": False, "status": {}, "width": 270, "height": 90, "x": x, "y": y,
            "owner": current_user
        }
        layout_data.setdefault('items', []).append(new_project)
        
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout_data, f, indent=4)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/remove_project_from_layout/<project_id>', methods=['DELETE'])
@admin_required
def remove_project_from_layout(project_id):
    """Removes a project from the layout JSON file."""
    project_id = os.path.basename(project_id)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        layout_data = {"items": [], "background": {}}
        if os.path.exists(layout_path):
            try:
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Corrupt layout file."}), 500
        
        item_to_remove, error = check_layout_item_ownership(project_id, layout_data, current_user)
        if error: return error
        
        updated_items = [item for item in layout_data.get('items', []) if not (item.get('type') == 'project' and item.get('name') == project_id)]
        layout_data['items'] = updated_items
        
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout_data, f, indent=4)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/move_project_to_layout', methods=['POST'])
@admin_required
def move_project_in_layout():
    """Updates the x, y coordinates for a project."""
    data = request.json
    project_name = data.get('project_name')
    x, y = data.get('x'), data.get('y')

    if not all([project_name, x is not None, y is not None]):
        return jsonify({"status": "error", "message": "Missing data"}), 400
    
    project_name = os.path.basename(project_name)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        layout_data = {"items": [], "background": {}}
        if os.path.exists(layout_path):
            try:
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Corrupt layout file."}), 500
        
        item_to_move, error = check_layout_item_ownership(project_name, layout_data, current_user)
        if error: return error
        
        item_to_move['x'] = x
        item_to_move['y'] = y
        
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout_data, f, indent=4)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500