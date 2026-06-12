-- Runs once on first container init (as the postgres superuser).
-- Creates the application's NON-superuser role so that Row Level Security is
-- actually enforced (a superuser / BYPASSRLS role would silently ignore it).
CREATE ROLE gbd_app WITH LOGIN PASSWORD 'gbd_app' CREATEDB NOSUPERUSER NOBYPASSRLS;
CREATE DATABASE gbd OWNER gbd_app;
GRANT ALL PRIVILEGES ON DATABASE gbd TO gbd_app;
