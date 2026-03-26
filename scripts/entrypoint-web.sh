# Entrypoint for web container (nginx + gunicorn via supervisord)
exec supervisord -c /etc/supervisord_web.conf
