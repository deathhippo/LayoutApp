import os
from flask import Blueprint, send_from_directory, current_app, abort
from .auth import login_required # Import login_required if the parts page needs login

# You could define a prefix like '/parts' but let's keep it simple for now
bp = Blueprint('parts', __name__)

@bp.route('/parts/<project_id>')

def serve_parts_page(project_id):
    """Serves the parts HTML file for a specific project."""
    # Basic validation: ensure project_id looks reasonable (e.g., not trying path traversal)
    if not project_id or '/' in project_id or '\\' in project_id or '.' in project_id:
         abort(404) # Not found or invalid project ID format

    # Serve the parts.html file from the application root
    # Note: project_id isn't directly used here, JavaScript will fetch data using it
    return send_from_directory(current_app.config['APP_ROOT'], 'parts.html')
