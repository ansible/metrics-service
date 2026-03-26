#!/bin/bash
# Entrypoint for dispatcherd container (dispatcherd via supervisord)
exec supervisord -c /etc/supervisord_dispatcherd.conf
