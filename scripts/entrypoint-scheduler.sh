# Entrypoint for scheduler container (scheduler via supervisord)
exec supervisord -c /etc/supervisord_scheduler.conf
