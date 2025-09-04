web: python manage.py runserver 0.0.0.0:$PORT
worker: python manage.py run_dispatcher --workers=2 --timeout=3600
scheduler: python manage.py run_task_scheduler