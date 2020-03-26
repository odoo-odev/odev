-- -----------------------------------------------------------------------------
-- PS-Tech curated script to neutralize a database and making it suitable for
-- custom developments.
--
-- This script runs *after* all standard scripts and only on database running
-- a version of Odoo older than 15.0.
-- -----------------------------------------------------------------------------

-- DATABASE CONFIGURATION ------------------------------------------------------

-- remove expiration date
UPDATE ir_config_parameter
SET value = '2095-12-21'
WHERE key = 'database.expiration_date';
