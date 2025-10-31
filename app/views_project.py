import os
import json
import uuid
import sqlite3
from datetime import datetime, timezone
from flask import (
    Blueprint, jsonify, request, session, current_app
)
from .auth import login_required, admin_required
from .db import get_db_connection
from .helpers import check_layout_item_ownership, update_project_status, get_project_inventory_status

# All routes here will be prefixed with /api
# e.g., @bp.route('/project/<id>/...') becomes /api/project/<id>/...
bp = Blueprint('project', __name__, url_prefix='/api')

# --- Photo Routes ---
# ... (upload_project_photo, get_project_photos, delete_project_photo remain the same) ...
@bp.route('/project/<project_id>/upload', methods=['POST'])
@admin_required
def upload_project_photo(project_id):
    # --- Code is identical to previous version ---
    if 'photo' not in request.files: return jsonify({"status": "error", "message": "No photo part"}), 400
    file = request.files['photo']
    if file.filename == '': return jsonify({"status": "error", "message": "No selected file"}), 400
    
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
    except Exception: layout_data = {}
    
    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    if error: return error
    
    conn = None
    try:
        project_id = os.path.basename(project_id)
        project_upload_path = os.path.join(current_app.config['UPLOADS_FOLDER'], project_id)
        os.makedirs(project_upload_path, exist_ok=True)
        _, f_ext = os.path.splitext(file.filename)
        secure_name = f"{uuid.uuid4().hex}{f_ext}"
        filepath = os.path.join(project_upload_path, secure_name)
        file.save(filepath)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT INTO project_photos (project_task_no, filename, uploaded_at) VALUES (?, ?, ?)", (project_id, secure_name, timestamp))
        conn.commit()
        return jsonify({"status": "success", "filename": secure_name})
    except Exception as e:
        return jsonify({"status": "error", "message": "File upload failed"}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/photos')
@login_required
def get_project_photos(project_id):
    # --- Code is identical to previous version ---
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        photos = conn.execute("SELECT filename, uploaded_at FROM project_photos WHERE project_task_no = ? ORDER BY uploaded_at DESC", (project_id,)).fetchall()
        photo_list = [{"url": f"/uploads/{project_id}/{row['filename']}", "filename": row['filename'], "uploaded_at": row['uploaded_at']} for row in photos]
        return jsonify(photo_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/photo/<filename>', methods=['DELETE'])
@admin_required
def delete_project_photo(project_id, filename):
    # --- Code is identical to previous version ---
    project_id = os.path.basename(project_id)
    filename = os.path.basename(filename)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
    except Exception: layout_data = {}
    
    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    if error: return error
    
    conn = None
    try:
        filepath = os.path.join(current_app.config['UPLOADS_FOLDER'], project_id, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("DELETE FROM project_photos WHERE project_task_no = ? AND filename = ?", (project_id, filename))
        conn.commit()
        return jsonify({"status": "success", "message": "Photo deleted."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- Project Data Routes ---
@bp.route('/project/<project_id>/extra_details')
@login_required
def get_project_extra_details(project_id):
    # --- Code is identical to previous version ---
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        notes_row = conn.execute("SELECT notes, electrification_notes, control_notes FROM project_notes WHERE project_task_no = ?", (project_id,)).fetchone()
        details = {"notes": dict(notes_row) if notes_row else {"notes": "", "electrification_notes": "", "control_notes": ""}}
        return jsonify(details)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

# --- MODIFIED FUNCTION ---
@bp.route('/project/<project_id>/work_orders')
@login_required
def get_project_work_orders(project_id):
    """
    Fetches work orders (DNIs) for a project, including completion status
    and the source of completion (manual, auto, both).
    """
    main_conn, montaza_conn, cas_conn = None, None, None
    try:
        project_id = os.path.basename(project_id) # Sanitize
        main_conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if main_conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        # Get all work orders for this project and work center
        work_orders = [dict(row) for row in main_conn.execute(
            "SELECT work_order_no, description FROM work_orders WHERE project_task_no = ? AND work_center = ? ORDER BY work_order_no",
            (project_id, sklop)
        )]
        
        if not work_orders: return jsonify([]) # No work orders found
        
        dni_numbers = [wo['work_order_no'] for wo in work_orders]
        placeholders_dni = ','.join('?' * len(dni_numbers))
        
        # --- Step 1: Get MANUALLY completed DNIs (from velika_montaza) ---
        montaza_conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        manual_completed_set = set()
        if montaza_conn:
            try:
                manual_completed_set = {row['work_order_no'] for row in montaza_conn.execute(
                    "SELECT work_order_no FROM dni_status WHERE project_task_no = ? AND is_completed = 1", (project_id,)
                )}
            except Exception as e_m:
                 print(f"Warning: Could not query montaza DB for manual DNI status: {e_m}")
        else:
             print(f"Warning: Montaza DB not connected for manual DNI status.")


        # --- Step 2: Get AUTOMATICALLY completed DNIs (from cas_baza) ---
        auto_completed_set = set()
        cas_conn = get_db_connection(current_app.config['CAS_DATABASE_FILE_PATH'])
        if cas_conn:
            try:
                # Ensure placeholders_dni is not empty before querying
                if placeholders_dni:
                    query_cas = f"""
                        SELECT DISTINCT ref_doc_no 
                        FROM time_entries 
                        WHERE ref_doc_no IN ({placeholders_dni}) 
                        AND event_type = 'Zaključi'
                    """
                    auto_completed_set = {row['ref_doc_no'] for row in cas_conn.execute(query_cas, dni_numbers)}
                else:
                    print(f"Warning: No DNI numbers found for project {project_id} to check in CAS DB.")

            except sqlite3.OperationalError as e_c:
                print(f"Warning: Could not query cas_baza for auto-completion: {e_c}")
        else:
             print(f"Warning: CAS DB not connected for auto DNI status.")
        
        # --- Step 3: Combine and Determine Source ---
        for wo in work_orders:
            wo_no = wo['work_order_no']
            is_manual = wo_no in manual_completed_set
            is_auto = wo_no in auto_completed_set
            
            wo['is_completed'] = is_manual or is_auto # Mark completed if either is true

            # Determine the source
            if is_manual and is_auto:
                wo['completion_source'] = 'both'
            elif is_manual:
                wo['completion_source'] = 'manual'
            elif is_auto:
                wo['completion_source'] = 'auto'
            else:
                 wo['completion_source'] = 'none'

        return jsonify(work_orders)
    except Exception as e:
        print(f"Error fetching work orders for {project_id}: {e}")
        # Return empty list or error object? Let's return error object for better debugging
        return jsonify({"error": f"Failed to fetch work orders: {str(e)}"}), 500
    finally:
        # Ensure all connections are closed
        if main_conn: main_conn.close()
        if montaza_conn: montaza_conn.close()
        if cas_conn: cas_conn.close()
# --- END MODIFIED FUNCTION ---


@bp.route('/project/<project_id>/missing_parts')
@login_required
def get_project_missing_parts(project_id):
    # --- Code is identical to previous version ---
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        query = """ SELECT item_no, description FROM components WHERE project_task_no = ? AND (inventory <= 0 OR inventory IS NULL OR inventory = '') AND (remaining_quantity > 0 OR remaining_quantity IS NULL) AND work_center != ? GROUP BY item_no ORDER BY item_no """
        missing_parts = [dict(row) for row in conn.execute(query, (project_id, sklop)).fetchall()]
        return jsonify(missing_parts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/detailed_missing_parts')
# NO login required for this public page
def get_project_detailed_missing_parts(project_id):
    """
    Fetches a detailed list of missing parts for the public parts.html page.
    """
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        
        # This query is for the detailed parts.html page
        query = """ 
            SELECT 
                item_no, 
                description, 
                sifra_regala, 
                remaining_quantity as quantity_needed 
            FROM components 
            WHERE project_task_no = ? 
              AND (inventory <= 0 OR inventory IS NULL OR inventory = '') 
              AND (remaining_quantity > 0 OR remaining_quantity IS NULL) 
              AND work_center != ? 
            GROUP BY item_no, description, sifra_regala, remaining_quantity 
            ORDER BY item_no 
        """
        
        missing_parts = [dict(row) for row in conn.execute(query, (project_id, sklop)).fetchall()]
        return jsonify(missing_parts)
    except Exception as e:
        print(f"Error fetching detailed missing parts for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()
        
@bp.route('/project/<project_id>/arrived_parts')
@login_required
def get_project_arrived_parts(project_id):
    # --- Code is identical to previous version ---
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        query = """ SELECT item_no, description as part, sifra_regala as location FROM components WHERE project_task_no = ? AND inventory > 0 AND (remaining_quantity > 0 OR remaining_quantity IS NULL) AND work_center != ? ORDER BY item_no """
        arrived_parts = [dict(row) for row in conn.execute(query, (project_id, sklop)).fetchall()]
        return jsonify(arrived_parts)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/detailed_arrived_parts')
# NO login required for this public page
def get_project_detailed_arrived_parts(project_id):
    """
    Fetches a detailed list of ARRIVED parts for the public parts.html page.
    """
    conn = None
    try:
        project_id = os.path.basename(project_id)
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        
        # This query is for the detailed parts.html page, for ARRIVED parts
        query = """ 
            SELECT 
                item_no, 
                description, 
                sifra_regala, 
                remaining_quantity as quantity_needed 
            FROM components 
            WHERE project_task_no = ? 
              AND inventory > 0  -- This is the "arrived" logic
              AND (remaining_quantity > 0 OR remaining_quantity IS NULL) 
              AND work_center != ? 
            GROUP BY item_no, description, sifra_regala, remaining_quantity 
            ORDER BY item_no 
        """
        
        arrived_parts = [dict(row) for row in conn.execute(query, (project_id, sklop)).fetchall()]
        return jsonify(arrived_parts)
    except Exception as e:
        print(f"Error fetching detailed arrived parts for {project_id}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()
@bp.route('/project_inventory_status/<project_id>')
@login_required
def get_project_inventory_status_api(project_id):
    # --- Code is identical to previous version ---
    try:
        project_id = os.path.basename(project_id)
        statuses = get_project_inventory_status(project_id) # Uses helper
        return jsonify(statuses)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Project Action Routes (POST/PUT/DELETE) ---
@bp.route('/project/<project_id>/details', methods=['POST'])
@admin_required
def update_project_details(project_id):
    # --- Code is identical to previous version ---
    data = request.json
    new_details = data.get('details')
    if new_details is None: return jsonify({"status": "error", "message": "Missing 'details'"}), 400
    
    project_id = os.path.basename(project_id)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        layout_data = {}
        if os.path.exists(layout_path):
             # Ensure file exists before trying to open read-write
            with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
        else:
             # Handle case where layout file doesn't exist yet
             print(f"Warning: Layout file not found at {layout_path} during details update.")
             # Depending on desired behavior, could return error or proceed if item found later
             # For now, let's allow proceeding, assuming item might be added soon.
             pass # layout_data remains {}


        item_to_update, error = check_layout_item_ownership(project_id, layout_data, current_user)
        
        # If the item wasn't found in the layout_data (even if file existed)
        if error and error[1] == 404:
             print(f"Warning: Project {project_id} not found in layout during details update. Cannot save.")
             # Return the original 404 error from the helper
             return error
        elif error: # Handle other errors like permission denied
             return error
        
        # If item_to_update is None but no error (e.g., file didn't exist), we still can't update.
        if item_to_update is None:
             print(f"Error: Could not find item {project_id} to update details, possibly due to missing layout file.")
             return jsonify({"status": "error", "message": "Project not found in layout data."}), 404


        item_to_update['details'] = new_details
        
        # Now save the updated layout_data
        with open(layout_path, 'w', encoding='utf-8') as f:
            json.dump(layout_data, f, indent=4)
        
        print(f"Updated details for project {project_id} in layout by user '{current_user}'.")
        return jsonify({"status": "success"})

    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {layout_path} during details update.")
        return jsonify({"status": "error", "message": "Layout file is corrupted."}), 500
    except FileNotFoundError: # Should be caught by earlier check, but just in case
        print(f"Error: Layout file {layout_path} not found during details update attempt.")
        return jsonify({"status": "error", "message": "Layout file not found."}), 500
    except Exception as e:
        print(f"Error updating details for project {project_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route('/project/<project_id>/priority', methods=['POST'])
@admin_required
def set_project_priority(project_id):
    # --- Code is identical to previous version ---
    data = request.json
    priority = data.get('priority')
    project_id = os.path.basename(project_id)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        # Load layout data to check ownership
        layout_data = {}
        if os.path.exists(layout_path):
            with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
        else:
             print(f"Warning: Layout file not found at {layout_path} during priority set.")
             # Allow setting priority even if not in layout? Maybe. Check ownership helper behavior.
             pass
    except json.JSONDecodeError:
         print(f"Warning: Could not read layout file {layout_path} due to JSON error during priority set.")
         # Proceed, but ownership check might fail if layout_data is empty
         layout_data = {}
    except Exception as e:
        print(f"Warning: Error loading layout file {layout_path} during priority set: {e}")
        layout_data = {}


    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    # Allow setting priority even if not found in layout? Let's allow it for now.
    if error and error[1] != 404: # Block only on permission denied, not on 'not found'
        return error
    
    if priority not in ['Low', 'Normal', 'High', 'Urgent']:
        return jsonify({"status": "error", "message": "Invalid priority"}), 400
    
    # Use helper function which handles DB connection
    return update_project_status(project_id, 'priority', priority)

@bp.route('/project/<project_id>/pause', methods=['POST'])
@admin_required
def set_project_pause_status(project_id):
    # --- Code is identical to previous version ---
    data = request.json
    pause_reason = data.get('reason')
    project_id = os.path.basename(project_id)
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        # Load layout data to check ownership
        layout_data = {}
        if os.path.exists(layout_path):
             with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
        else:
             print(f"Warning: Layout file not found at {layout_path} during pause set.")
             pass
    except json.JSONDecodeError:
         print(f"Warning: Could not read layout file {layout_path} due to JSON error during pause set.")
         layout_data = {}
    except Exception as e:
        print(f"Warning: Error loading layout file {layout_path} during pause set: {e}")
        layout_data = {}

    
    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    # Allow setting status even if not found in layout?
    if error and error[1] != 404: # Block only on permission denied
        return error
    
    allowed_reasons = ['Missing Parts', 'Construction Error', 'Paused', None]
    if pause_reason not in allowed_reasons:
        return jsonify({"status": "error", "message": "Invalid pause reason"}), 400
    
    # Use helper function
    return update_project_status(project_id, 'pause_status', pause_reason)

@bp.route('/dni/<work_order_no>/status', methods=['POST'])
@admin_required
def update_dni_status(work_order_no):
    # --- Code is identical to previous version ---
    # NOTE: This endpoint ONLY updates the MANUAL status in velika_montaza.db
    # It does NOT affect the automatic status derived from cas_baza.db
    data = request.json
    project_id = data.get('project_task_no')
    work_order_no = os.path.basename(work_order_no)
    if not project_id: return jsonify({"status": "error", "message": "Missing project_task_no"}), 400
    
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        # Load layout data to check ownership
        layout_data = {}
        if os.path.exists(layout_path):
             with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
        else:
             print(f"Warning: Layout file not found at {layout_path} during DNI status update.")
             pass # Allow update even if project not in layout
    except json.JSONDecodeError:
         print(f"Warning: Could not read layout file {layout_path} due to JSON error during DNI status update.")
         layout_data = {} # Proceed but ownership check might behave unexpectedly
    except Exception as e:
        print(f"Warning: Error loading layout file {layout_path} during DNI status update: {e}")
        layout_data = {}

    
    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    if error and error[1] != 404: # Allow if not in layout, but fail on permission denied
        return error
    
    conn = None
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        
        # Insert or Replace the MANUAL status record
        conn.execute("INSERT OR REPLACE INTO dni_status (work_order_no, project_task_no, description, is_completed) VALUES (?, ?, ?, ?)",
                     (work_order_no, project_id, data.get('description', ''), 1 if data.get('completed') else 0))
        
        # Update last DNI update timestamp for the project
        conn.execute("INSERT OR IGNORE INTO project_notes (project_task_no) VALUES (?)", (project_id,))
        conn.execute("UPDATE project_notes SET last_dni_updated_at = ? WHERE project_task_no = ?", (timestamp, project_id))
        conn.commit()
        print(f"Updated MANUAL DNI status for {work_order_no} (Project: {project_id}) by user '{current_user}'")
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error updating DNI status for {work_order_no}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/notes', methods=['POST'])
@admin_required
def save_project_notes(project_id):
    # --- Code is identical to previous version ---
    data = request.json
    project_id = os.path.basename(project_id)
    note_type, content = data.get('note_type'), data.get('content')
    current_user = session.get('username')
    layout_path = current_app.config['LAYOUT_DATA_FILE_PATH']
    try:
        # Load layout data to check ownership
        layout_data = {}
        if os.path.exists(layout_path):
             with open(layout_path, 'r', encoding='utf-8') as f: layout_data = json.load(f)
        else:
            print(f"Warning: Layout file not found at {layout_path} during notes save.")
            pass # Allow saving notes even if project not in layout
    except json.JSONDecodeError:
         print(f"Warning: Could not read layout file {layout_path} due to JSON error during notes save.")
         layout_data = {}
    except Exception as e:
        print(f"Warning: Error loading layout file {layout_path} during notes save: {e}")
        layout_data = {}

    
    item, error = check_layout_item_ownership(project_id, layout_data, current_user)
    if error and error[1] != 404: return error # Block on permission denied
    
    if note_type not in ['notes', 'electrification_notes', 'control_notes']:
        return jsonify({"status": "error", "message": "Invalid note type"}), 400
    
    conn = None
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT OR IGNORE INTO project_notes (project_task_no) VALUES (?)", (project_id,))
        conn.execute(f"UPDATE project_notes SET {note_type} = ?, last_note_updated_at = ? WHERE project_task_no = ?", (content, timestamp, project_id))
        conn.commit()
        print(f"Saved notes (type: {note_type}) for project {project_id} by user '{current_user}'")
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error saving notes for {project_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/electrify', methods=['POST'])
@admin_required
def electrify_project(project_id):
    # --- Code is identical to previous version ---
    project_id = os.path.basename(project_id)
    # Ownership check... (Add like other POST routes if needed, depends if status should be settable if not in layout)
    # For now, assuming ownership check via helper is sufficient if called
    return update_project_status(project_id, 'electrification_status', 'Ready')

@bp.route('/project/<project_id>/control', methods=['POST'])
@admin_required
def control_project(project_id):
    # --- Code is identical to previous version ---
    project_id = os.path.basename(project_id)
    # Ownership check...
    return update_project_status(project_id, 'control_status', 'Ready')

@bp.route('/project/<project_id>/complete/<task_type>', methods=['POST'])
@admin_required
def complete_task(project_id, task_type):
    # --- Code is identical to previous version ---
    project_id = os.path.basename(project_id)
    task_type = os.path.basename(task_type)
    # Ownership check...
    if task_type not in ['electrification', 'control']: return jsonify({"status": "error", "message": "Invalid task type"}), 400
    
    timestamp = datetime.now(timezone.utc).isoformat()
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT OR IGNORE INTO project_notes (project_task_no) VALUES (?)", (project_id,))
        conn.execute(f"UPDATE project_notes SET {task_type}_completed_at = ? WHERE project_task_no = ?", (timestamp, project_id))
        conn.commit()
        
        # Check if both are completed
        row = conn.execute("SELECT electrification_completed_at, control_completed_at FROM project_notes WHERE project_task_no = ?", (project_id,)).fetchone()
        if row and row['electrification_completed_at'] and row['control_completed_at']:
            conn.execute("UPDATE project_notes SET packaging_status = ? WHERE project_task_no = ?", ('Ready', project_id))
            conn.commit()
            print(f"Project {project_id} marked ready for packaging.")

        print(f"Completed {task_type} for project {project_id} by user '{session['username']}'")
        return jsonify({"status": "success", "timestamp": timestamp})
    except Exception as e:
        print(f"Error completing {task_type} for {project_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

@bp.route('/project/<project_id>/reset_task/<task_type>', methods=['POST'])
@admin_required
def reset_task(project_id, task_type):
    # --- Code is identical to previous version ---
    project_id = os.path.basename(project_id)
    task_type = os.path.basename(task_type)
    # Ownership check...
    if task_type not in ['electrification', 'control']: return jsonify({"status": "error", "message": "Invalid task type"}), 400
    
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT OR IGNORE INTO project_notes (project_task_no) VALUES (?)", (project_id,))
        # Reset status, completed_at, and packaging status if either task is reset
        conn.execute(f"UPDATE project_notes SET {task_type}_status = ?, {task_type}_completed_at = ?, packaging_status = ? WHERE project_task_no = ?", (None, None, None, project_id))
        conn.commit()
        print(f"Reset {task_type} status for project {project_id} by user '{session['username']}'")
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error resetting {task_type} for {project_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

# --- (Make sure check_layout_item_ownership, update_project_status, get_project_inventory_status are imported from helpers) ---

