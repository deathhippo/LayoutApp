from flask import Flask
from flask_cors import CORS
import os

def create_app():
    """The Application Factory"""

    app = Flask(__name__)

    # 1. Load Configuration
    app.config.from_object('app.config')

    # 2. Initialize Extensions
    CORS(app)
    app.secret_key = app.config['SECRET_KEY']

    # 3. Initialize Database
    from . import db
    db.init_app(app) # Register DB functions with the app

    # 4. Register (Link) the Blueprints

    # Register Auth Blueprint
    from . import auth
    app.register_blueprint(auth.bp)

    # Register Core Views Blueprint
    from . import views_core
    app.register_blueprint(views_core.bp)

    # Register Layout Views Blueprint
    from . import views_layout
    app.register_blueprint(views_layout.bp)

    # Register Project Views Blueprint
    from . import views_project
    app.register_blueprint(views_project.bp)

    # Register Admin Views Blueprint
    from . import views_admin
    app.register_blueprint(views_admin.bp)

    # *** THIS LINE WAS MISSING ***
    # Register Parts View Blueprint
    from . import views_parts
    app.register_blueprint(views_parts.bp)
    # *** END MISSING LINE ***

    print("Application created and blueprints registered.")

    return app

