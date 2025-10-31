import os
import json
from datetime import datetime
from flask import (
    Blueprint, jsonify, request, send_from_directory, current_app
)
from .auth import login_required, admin_required # Import decorators from auth.py
from .helpers import ( # Import helpers from helpers.py
    get_project_statuses_from_db, get_completion_data_from_db,
    get_latest_worker_from_cas_db, get_photo_info_from_db,
    check_notes_existence_from_db, get_task_display_status
)

# Create a Blueprint named 'core'. Routes defined here will be accessible
# without a specific prefix (like / or /planning) unless added in the route decorator.
bp = Blueprint('core', __name__)

# --- Web App Serving Routes ---
@bp.route('/')
def serve_app():
    """Serves the main HTML application file (mobile_app.html)."""
    # Uses APP_ROOT from config to find the file in the project's root folder.
    return send_from_directory(current_app.config['APP_ROOT'], 'mobile_app.html')

@bp.route('/planning')
def serve_planning_page():
    """Serves the planning HTML file (planning.html)."""
    # Uses APP_ROOT from config to find the file in the project's root folder.
    return send_from_directory(current_app.config['APP_ROOT'], 'planning.html')

@bp.route('/admin')
@login_required # Ensures the user is logged in.
@admin_required # Ensures the logged-in user has the 'admin' role.
def serve_admin_page():
    """Serves the admin control panel HTML file (admin.html)."""
    # The decorators handle authentication and authorization.
    # Uses APP_ROOT from config to find the file in the project's root folder.
    return send_from_directory(current_app.config['APP_ROOT'], 'admin.html')

@bp.route('/uploads/<project_id>/<filename>')
@login_required # Ensures the user is logged in to view uploaded files.
def serve_uploaded_file(project_id, filename):
    """Serves uploaded project photos from the uploads folder."""
    # Sanitize inputs to prevent directory traversal issues.
    project_id = os.path.basename(project_id)
    filename = os.path.basename(filename)
    # Construct the path to the specific project's upload folder.
    project_upload_path = os.path.join(current_app.config['UPLOADS_FOLDER'], project_id)
    # Check if the project folder exists.
    if not os.path.isdir(project_upload_path):
        return "Project upload folder not found", 404
    # Serve the requested file from that project's folder.
    return send_from_directory(project_upload_path, filename)

# --- Main API Data Endpoints ---
@bp.route('/api/layout_data')
@login_required # Requires login to fetch layout data.
def get_layout_data():
    """Fetches layout data from JSON and combines it with project statuses from DB."""
    try:
        # Get the full path to the layout JSON file from config.
        layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
        # If the file doesn't exist, create an empty one.
        if not os.path.exists(layout_path):
            print(f"Warning: Layout file not found. Creating an empty one.")
            with open(layout_path, 'w', encoding='utf-8') as f:
                json.dump({"items": [], "background": {}}, f, indent=4)
        
        # Read the layout data from the JSON file.
        with open(layout_path, 'r', encoding='utf-8') as f: data = json.load(f)
        # Add the current server time to the data.
        data['server_timestamp'] = datetime.now().strftime('%H:%M:%S')

        # Get a list of project IDs that are present in the layout file.
        project_ids_in_layout = [item['name'] for item in data.get('items', []) if item.get('type') == 'project']

        # If there are projects in the layout, fetch their statuses and details.
        if project_ids_in_layout:
            # Fetch DNI completion statuses using the helper function.
            statuses = get_project_statuses_from_db(project_ids_in_layout)
            # Fetch task completion data (electrification, control, etc.) using the helper.
            completion_data = get_completion_data_from_db(project_ids_in_layout)
            # Fetch the latest worker associated with each project using the helper.
            latest_workers = get_latest_worker_from_cas_db(project_ids_in_layout)

            # Iterate through the items in the layout data again.
            for item in data.get('items', []):
                # If the item is a project...
                if item.get('type') == 'project':
                    name = item.get('name')
                    # Add its DNI status if found.
                    if name in statuses: item['status'] = statuses[name]
                    # Add its task completion data if found.
                    if name in completion_data: item.update(completion_data[name])
                    # Update its 'details' field with the latest worker if found.
                    if name in latest_workers:
                        item['details'] = latest_workers[name]
        # Return the combined data as JSON.
        return jsonify(data)
    except Exception as e:
        # Log any errors and return a server error response.
        print(f"Error fetching layout data: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/planning_data')
# @login_required # Uncomment if planning data requires login
def get_planning_data():
    """Gathers comprehensive data ONLY for projects PRESENT IN THE LAYOUT."""
    try:
        # Get the path to the layout file.
        layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
        projects_in_layout_info = {} # Store owner and manually set details.
        project_ids_in_layout = [] # List of project names found in the layout.
        
        # Check if the layout file exists.
        if os.path.exists(layout_path):
            try:
                # Read the layout file content.
                with open(layout_path, 'r', encoding='utf-8') as f:
                    layout_data_content = json.load(f)
                    # Loop through items to find projects.
                    for item in layout_data_content.get('items', []):
                        if item.get('type') == 'project':
                            project_name = item.get('name')
                            if project_name:
                                # Store details and owner from the layout item.
                                projects_in_layout_info[project_name] = {
                                    'details': item.get('details', 'N/A'),
                                    'owner': item.get('owner', None)
                                }
                                project_ids_in_layout.append(project_name)
            except json.JSONDecodeError:
                # Handle error if the JSON is invalid.
                return jsonify({"error": "Invalid JSON in layout file."}), 500
        else:
            # If layout file doesn't exist, return empty list.
            return jsonify([])
        
        # If no projects were found in the layout, return empty list.
        if not project_ids_in_layout: return jsonify([])

        # Sort the project IDs alphabetically.
        project_ids_in_layout.sort()
        # Fetch various data points for these projects using helper functions.
        dni_statuses = get_project_statuses_from_db(project_ids_in_layout)
        completion_data = get_completion_data_from_db(project_ids_in_layout)
        photo_info = get_photo_info_from_db(project_ids_in_layout)
        notes_existence = check_notes_existence_from_db(project_ids_in_layout)
        latest_workers = get_latest_worker_from_cas_db(project_ids_in_layout)

        planning_list = [] # List to hold the final data for each project.
        # Iterate through the projects found in the layout.
        for proj_id in project_ids_in_layout:
            # Get the fetched data for the current project ID, defaulting to empty dicts.
            comp_info = completion_data.get(proj_id, {})
            p_info = photo_info.get(proj_id, {})
            layout_info = projects_in_layout_info.get(proj_id, {})
            
            # Collect all relevant timestamps to find the most recent update.
            timestamps = [
                comp_info.get('electrification_completed_at'),
                comp_info.get('control_completed_at'),
                comp_info.get('last_note_updated_at'),
                comp_info.get('last_dni_updated_at'),
                p_info.get('last_photo_upload')
            ]
            valid_timestamps = [ts for ts in timestamps if ts] # Filter out None values.
            last_updated = max(valid_timestamps) if valid_timestamps else None # Find the latest timestamp.
            
            # Prioritize worker name from CAS DB, fallback to layout details.
            worker_name = latest_workers.get(proj_id, layout_info.get('details', 'N/A'))

            # Construct the data object for the planning view for this project.
            proj_data = {
                "name": proj_id,
                "worker": worker_name,
                "owner": layout_info.get('owner', None),
                "status_percentage": dni_statuses.get(proj_id, {}).get('percentage', 0),
                "priority": comp_info.get('priority', 'Low'),
                "pause_status": comp_info.get('pause_status', None),
                "electrification_status": get_task_display_status(comp_info, 'electrification'),
                "control_status": get_task_display_status(comp_info, 'control'),
                "packaging_status": comp_info.get('packaging_status', None),
                "has_notes": notes_existence.get(proj_id, False),
                "photo_count": p_info.get('photo_count', 0),
                "last_updated_at": last_updated
            }
            planning_list.append(proj_data)
        # Return the list of project data for the planning view.
        return jsonify(planning_list)
    except Exception as e:
        # Log errors and return a server error response.
        print(f"Error fetching planning data: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/api/get_image')
@login_required # Requires login to fetch background image.
def get_image():
    """Serves the background layout image specified by the 'path' query parameter."""
    filename = request.args.get('path')
    if not filename: return "Missing path parameter", 400
    # Sanitize filename.
    filename = os.path.basename(filename)
    # Construct path relative to the app root.
    image_path = os.path.join(current_app.config['APP_ROOT'], filename)
    # Check if image exists and serve it.
    if os.path.exists(image_path):
        return send_from_directory(current_app.config['APP_ROOT'], filename)
    else:
        # Log warning if image not found.
        print(f"Warning: Image not found at {image_path}")
        return "Image not found", 404

# --- NEW Static File Serving Routes ---

@bp.route('/css/<path:filename>')
def serve_css(filename):
    """Serves CSS files from the 'css' directory in the project root."""
    # Construct the path to the 'css' directory.
    css_dir = os.path.join(current_app.config['APP_ROOT'], 'css')
    # Use send_from_directory for security and proper MIME type handling.
    return send_from_directory(css_dir, filename)

@bp.route('/js/<path:filename>')
def serve_js(filename):
    """Serves JavaScript files from the 'js' directory in the project root."""
    # Construct the path to the 'js' directory.
    js_dir = os.path.join(current_app.config['APP_ROOT'], 'js')
    # Use send_from_directory for security and proper MIME type handling.
    return send_from_directory(js_dir, filename)
