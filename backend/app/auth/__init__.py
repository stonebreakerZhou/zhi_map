"""Email registration / login subsystem.

Decoupled from the rest of the backend:
- Own router mounted at /api/auth/*
- Own tables (auth_email_credentials, auth_email_verifications)
- Does NOT touch the anonymous user() dependency in main.py
- Anonymous → registered migration lives here
"""