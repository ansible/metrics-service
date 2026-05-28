-- Create Redash database and user (loaded by PostgreSQL on first boot)
CREATE ROLE redash LOGIN PASSWORD 'redash';
CREATE DATABASE redash OWNER redash;
GRANT ALL PRIVILEGES ON DATABASE redash TO redash;
