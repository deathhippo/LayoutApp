import os
import json
import sqlite3
from datetime import datetime
from flask import jsonify, current_app
from .db import get_db_connection

# --- HELPER FUNCTION FOR OWNERSHIP CHECK ---
def check_layout_item_ownership(project_id, layout_data, current_user):
    """
    Checks if the current user owns the specified project item in the layout.
    Returns (item, error_response_tuple OR None)
    """
    item_found = None
    for item in layout_data.get('items', []):
        if item.get('type') == 'project' and item.get('name') == project_id:
            item_found = item
            break
    if not item_found:
        return None, (jsonify({"status": "warning", "message": "Project not found in layout"}), 404)
    item_owner = item_found.get('owner')
    if item_owner is None or item_owner == current_user:
        return item_found, None # Permission granted
    print(f"DENIED: User '{current_user}' tried to modify item '{project_id}' owned by '{item_owner}'.")
    return None, (jsonify({"status": "error", "message": f"Permission denied. This item is owned by '{item_owner}'."}), 403)

# --- MODIFIED HELPER FUNCTION FOR CAS DB - NOW LINKS THROUGH DNI ---
def get_latest_worker_from_cas_db(project_ids):
    if not project_ids: return {}
    latest_workers = {}
    main_conn = None
    cas_conn = None
    project_to_dni_map = {}
    try:
        # Step 1: Get DNIs from projekti_baza.db
        main_conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if main_conn is None:
            print(f"Warning: Could not connect to main DB to get DNIs for worker lookup.")
            return {}
        placeholders_proj = ','.join('?' * len(project_ids))
        dni_query = f"SELECT project_task_no, work_order_no FROM work_orders WHERE project_task_no IN ({placeholders_proj})"
        cursor_main = main_conn.cursor()
        cursor_main.execute(dni_query, project_ids)
        for row in cursor_main.fetchall():
            proj_id = row['project_task_no']
            dni_no = row['work_order_no']
            if proj_id not in project_to_dni_map:
                project_to_dni_map[proj_id] = []
            project_to_dni_map[proj_id].append(dni_no)
        # Step 2: Query cas_baza.db
        all_dni_numbers = [dni for dnis in project_to_dni_map.values() for dni in dnis]
        if not all_dni_numbers:
            return {}
        cas_conn = get_db_connection(current_app.config['CAS_DATABASE_FILE_PATH'])
        if cas_conn is None:
            print(f"Warning: Could not connect to CAS DB to get worker names.")
            return {}
        cursor_cas = cas_conn.cursor()
        placeholders_dni = ','.join('?' * len(all_dni_numbers))
        query_cas = f"""
            SELECT ref_doc_no, worker_name, MAX(event_datetime) as max_ts
            FROM time_entries
            WHERE ref_doc_no IN ({placeholders_dni})
            GROUP BY ref_doc_no
        """
        cursor_cas.execute(query_cas, all_dni_numbers)
        latest_entry_per_dni = {}
        for row in cursor_cas.fetchall():
            latest_entry_per_dni[row['ref_doc_no']] = {'worker': row['worker_name'], 'ts': row['max_ts']}
        for proj_id, dnis in project_to_dni_map.items():
            latest_ts_for_project = None
            latest_worker_for_project = None
            for dni in dnis:
                if dni in latest_entry_per_dni:
                    entry = latest_entry_per_dni[dni]
                    if latest_ts_for_project is None or entry['ts'] > latest_ts_for_project:
                        latest_ts_for_project = entry['ts']
                        latest_worker_for_project = entry['worker']
            if latest_worker_for_project:
                latest_workers[proj_id] = latest_worker_for_project
    except sqlite3.OperationalError as e:
        print(f"ERROR querying databases for worker lookup: {e}.")
    except Exception as e:
        print(f"Unexpected error fetching latest workers: {e}")
    finally:
        if main_conn: main_conn.close()
        if cas_conn: cas_conn.close()
    return latest_workers

def get_project_statuses_from_db(project_ids):
    if not project_ids: return {}
    placeholders_proj = ','.join('?' * len(project_ids))
    statuses = {}
    main_conn = None
    montaza_conn = None
    cas_conn = None
    try:
        # Step 1: Get TOTAL DNI count (from projekti_baza)
        main_conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if main_conn is None: raise sqlite3.OperationalError("Could not connect to main DB")
        totals_query = f"""
            SELECT project_task_no, COUNT(work_order_no) as total
            FROM work_orders
            WHERE project_task_no IN ({placeholders_proj}) AND work_center = ?
            GROUP BY project_task_no
        """
        totals = {r['project_task_no']: r['total'] for r in main_conn.execute(totals_query, project_ids + [current_app.config['UPRAVLJALNI_CENTER_SKLOP']])}
        # Step 2: Get ALL DNI numbers (from projekti_baza)
        all_dnis_query = f"""
            SELECT project_task_no, work_order_no 
            FROM work_orders
            WHERE project_task_no IN ({placeholders_proj}) AND work_center = ?
        """
        project_dni_map = {}
        all_dni_numbers_list = []
        for row in main_conn.execute(all_dnis_query, project_ids + [current_app.config['UPRAVLJALNI_CENTER_SKLOP']]):
            pid = row['project_task_no']
            dni = row['work_order_no']
            if pid not in project_dni_map:
                project_dni_map[pid] = set()
            project_dni_map[pid].add(dni)
            all_dni_numbers_list.append(dni)
        if not all_dni_numbers_list:
            for pid in project_ids:
                statuses[pid] = {"total": totals.get(pid, 0), "completed": 0, "percentage": 0}
            return statuses
        # Step 3: Get MANUALLY completed DNIs (from velika_montaza)
        montaza_conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        manual_completed_set = set()
        if montaza_conn:
            try:
                completeds_query_montaza = f"""
                    SELECT work_order_no 
                    FROM dni_status
                    WHERE project_task_no IN ({placeholders_proj}) AND is_completed = 1
                """
                manual_completed_set = {r['work_order_no'] for r in montaza_conn.execute(completeds_query_montaza, project_ids)}
            except Exception as e_montaza:
                print(f"ERROR accessing montaza DB for manual completed: {e_montaza}")
        # Step 4: Get AUTOMATICALLY completed DNIs (from cas_baza)
        cas_conn = get_db_connection(current_app.config['CAS_DATABASE_FILE_PATH'])
        auto_completed_set = set()
        if cas_conn:
            try:
                placeholders_dni_cas = ','.join('?' * len(all_dni_numbers_list))
                query_cas = f"""
                    SELECT DISTINCT ref_doc_no 
                    FROM time_entries 
                    WHERE ref_doc_no IN ({placeholders_dni_cas}) 
                    AND event_type = 'Zaključi'
                """
                auto_completed_set = {row['ref_doc_no'] for row in cas_conn.execute(query_cas, all_dni_numbers_list)}
            except sqlite3.OperationalError as e_cas:
                print(f"Warning: Could not query cas_baza for auto-completion status: {e_cas}")
        # Step 5: Combine and Calculate
        overall_completed_set = manual_completed_set.union(auto_completed_set)
        for pid in project_ids:
            total_tasks = totals.get(pid, 0)
            project_dnis = project_dni_map.get(pid, set())
            completed_dnis_for_project = project_dnis.intersection(overall_completed_set)
            completed_tasks = len(completed_dnis_for_project)
            percentage = round((completed_tasks * 100) / total_tasks) if total_tasks > 0 else 0
            statuses[pid] = {"total": total_tasks, "completed": completed_tasks, "percentage": percentage}
    except Exception as e:
        print(f"General error calculating project statuses: {e}")
        statuses = {pid: {"total": totals.get(pid, 0), "completed": 0, "percentage": 0} for pid in project_ids}
    finally:
        if main_conn: main_conn.close()
        if montaza_conn: montaza_conn.close()
        if cas_conn: cas_conn.close()
    return statuses

def get_completion_data_from_db(project_ids):
    if not project_ids: return {}
    placeholders = ','.join('?' * len(project_ids))
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        query = f"""
            SELECT project_task_no, electrification_status, control_status,
                   electrification_completed_at, control_completed_at,
                   packaging_status, priority, pause_status,
                   last_note_updated_at, last_dni_updated_at
            FROM project_notes
            WHERE project_task_no IN ({placeholders})
        """
        results = {row['project_task_no']: dict(row) for row in conn.execute(query, project_ids)}
        for pid in project_ids:
            if pid not in results: results[pid] = {}
        return results
    except Exception as e:
        print(f"Error fetching completion data: {e}")
        return {pid: {} for pid in project_ids}
    finally:
        if conn: conn.close()

def get_photo_info_from_db(project_ids):
    if not project_ids: return {}
    placeholders = ','.join('?' * len(project_ids))
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        query = f"SELECT project_task_no, COUNT(id) as photo_count, MAX(uploaded_at) as last_photo_upload FROM project_photos WHERE project_task_no IN ({placeholders}) GROUP BY project_task_no"
        results = {row['project_task_no']: dict(row) for row in conn.execute(query, project_ids)}
        for pid in project_ids:
            if pid not in results: results[pid] = {"photo_count": 0, "last_photo_upload": None}
        return results
    except Exception as e:
        print(f"Error fetching photo info: {e}")
        return {pid: {"photo_count": 0, "last_photo_upload": None} for pid in project_ids}
    finally:
        if conn: conn.close()

def check_notes_existence_from_db(project_ids):
    if not project_ids: return {}
    placeholders = ','.join('?' * len(project_ids))
    conn = None
    try:
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        query = f"SELECT project_task_no, (notes IS NOT NULL AND notes != '') OR (electrification_notes IS NOT NULL AND electrification_notes != '') OR (control_notes IS NOT NULL AND control_notes != '') as has_notes FROM project_notes WHERE project_task_no IN ({placeholders})"
        results = {row['project_task_no']: bool(row['has_notes']) for row in conn.execute(query, project_ids)}
        for pid in project_ids:
            if pid not in results: results[pid] = False
        return results
    except Exception as e:
        print(f"Error checking notes existence: {e}")
        return {pid: False for pid in project_ids}
    finally:
        if conn: conn.close()

def get_task_display_status(completion_info, task_type):
    if not completion_info: return "Pending"
    completed_at = completion_info.get(f"{task_type}_completed_at")
    status = completion_info.get(f"{task_type}_status")
    if completed_at:
        try:
            date_obj = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            return f"Completed ({date_obj.strftime('%d.%m.%y')})"
        except (ValueError, TypeError):
            return "Completed (Invalid Date)"
    elif status == 'Ready':
        return "Ready"
    else:
        return "Pending"

def update_project_status(project_id, column, status):
    conn = None
    try:
        project_id = os.path.basename(project_id)
        column = os.path.basename(column)
        allowed_columns = ['electrification_status', 'control_status', 'packaging_status', 'priority', 'pause_status']
        if column not in allowed_columns:
            raise ValueError(f"Invalid column name: {column}")
        conn = get_db_connection(current_app.config['VELIKA_MONTAZA_DB_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to montaza DB.")
        conn.execute("INSERT OR IGNORE INTO project_notes (project_task_no) VALUES (?)", (project_id,))
        conn.execute(f"UPDATE project_notes SET {column} = ? WHERE project_task_no = ?", (status, project_id))
        conn.commit()
        print(f"Updated {column} to {status} for project {project_id}")
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error updating project status ({column}) for {project_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()

def get_project_inventory_status(project_task_no):
    work_order_statuses = {}
    can_be_made_overall = True
    conn = None
    try:
        conn = get_db_connection(current_app.config['DATABASE_FILE_PATH'])
        if conn is None: raise sqlite3.OperationalError("Could not connect to main DB.")
        sklop = current_app.config['UPRAVLJALNI_CENTER_SKLOP']
        # 1. Get all components for this project's '303' work center
        components_query = "SELECT item_no, inventory FROM components WHERE project_task_no = ? AND work_center = ?"
        components = conn.execute(components_query, (project_task_no, sklop)).fetchall()
        if components:
            for comp in components:
                try:
                    inventory_val = float(comp['inventory']) if comp['inventory'] else 0.0
                except (ValueError, TypeError):
                    inventory_val = 0.0
                if inventory_val <= 0:
                    can_be_made_overall = False
                    break
        # 2. Get all work orders for this project's '303' work center
        work_orders_query = "SELECT work_order_no, description FROM work_orders WHERE project_task_no = ? AND work_center = ?"
        work_orders = conn.execute(work_orders_query, (project_task_no, sklop)).fetchall()
        # 3. Apply the overall status to ALL '303' work orders
        for wo in work_orders:
            work_order_statuses[wo['work_order_no']] = {
                "can_be_made": can_be_made_overall,
                "description": wo['description']
            }
    except sqlite3.OperationalError as e:
        print(f"Database error getting inventory status for {project_task_no}: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error getting inventory status for {project_task_no}: {e}")
        return {}
    finally:
        if conn: conn.close()
    return work_order_statuses