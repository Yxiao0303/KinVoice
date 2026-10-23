"""Default entry point: isolated C-CARE local prototype."""
from app.ccare.api import create_app

app = create_app()
