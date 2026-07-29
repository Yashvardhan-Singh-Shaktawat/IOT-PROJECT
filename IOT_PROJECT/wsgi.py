"""
WSGI config for IOT_PROJECT project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IOT_PROJECT.settings')

application = get_wsgi_application()

# Alias for Vercel Serverless Function entry point
app = application
