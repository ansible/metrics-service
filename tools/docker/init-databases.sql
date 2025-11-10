-- Create metrics_service database (for service orchestration)
-- This is created automatically by POSTGRES_DB env var, but we list it here for clarity

-- Create users needed for AWX dump restore (from metrics-utility)
CREATE USER myuser WITH PASSWORD 'mypassword';
CREATE USER awx WITH PASSWORD 'awx';

-- Grant role memberships so awx user can set ownership
GRANT myuser TO awx;

-- Create awx database (for mock AWX data collection testing)
CREATE DATABASE awx WITH OWNER awx;

-- Connect to awx database and grant schema permissions
\c awx
GRANT ALL ON SCHEMA public TO awx;
GRANT ALL ON SCHEMA public TO myuser;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE metrics_service TO metrics_service;
GRANT ALL PRIVILEGES ON DATABASE awx TO metrics_service;
GRANT ALL PRIVILEGES ON DATABASE awx TO awx;
GRANT ALL PRIVILEGES ON DATABASE awx TO myuser;
