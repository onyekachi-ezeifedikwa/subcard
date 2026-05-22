import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'subcard_v12.settings')
django.setup()

with connection.cursor() as cursor:
    cursor.execute("PRAGMA table_info(subcard_app_customuser)")
    columns = cursor.fetchall()
    for col in columns:
        print(col)
