-- -----------------------------------------------------------------------------
-- PS-Tech curated script to neutralize a database and making it suitable for
-- custom developments.
--
-- This script runs *before* all standard scripts.
-- -----------------------------------------------------------------------------

-- USERS AND ACCESS RIGHTS -----------------------------------------------------

-- find admin user and reset its login and password to 'admin'
WITH admin_candidates AS (

    -- priority 1: user associated to `base.user_admin` xmlid
    SELECT id, 1 AS priority, active
    FROM res_users
    WHERE id IN (
        SELECT res_id
        FROM ir_model_data
        WHERE model = 'res.users'
            AND (module, name) = ('base', 'user_admin')
    )

    UNION

    -- priority 2: user with login = 'admin'
    SELECT id, 2 as priority, active
    FROM res_users
    WHERE login = 'admin'

    UNION

    -- priority 3: users in the Administration/Settings group (`base.group_system`)
    SELECT id, 3 as priority, active
    FROM res_users
    WHERE id IN (
        SELECT uid
        FROM res_groups_users_rel
        WHERE gid IN (
            SELECT res_id
            FROM ir_model_data
            WHERE model = 'res.groups'
                AND (module, name) = ('base', 'group_system')
            )
        )

    UNION

    -- priority 99: any other user
    SELECT id, 99 as priority, active
    FROM res_users
)
UPDATE res_users
SET login = 'admin', password = 'admin'
WHERE id IN (
    SELECT id
    FROM admin_candidates
    WHERE active = TRUE
    ORDER BY priority ASC, id ASC
    LIMIT 1
);

-- reset password of first 50 other users to 'odoo'.
-- We are not doing all users because in some cases a module update will rehash all
-- passwords to pbkdf2 if they are not hashed, which is incredibly slow with many users
UPDATE res_users
SET password = 'odoo'
WHERE login != 'admin' AND id <= 53;

-- reset 2FA for all users
DO $$
BEGIN
IF EXISTS (
    SELECT *
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'res_users'
        AND column_name = 'totp_secret'
) THEN
    UPDATE res_users
    SET totp_secret = NULL;
END IF;
END $$;

-- remove existing 2FA policy
DELETE FROM ir_config_parameter
WHERE key = 'auth_totp.policy';

-- disable oauth providers
DO $$
BEGIN
IF EXISTS (
    SELECT *
    FROM information_schema.tables
    WHERE table_name = 'auth_oauth_provider'
) THEN
    UPDATE auth_oauth_provider
    SET enabled = false;
END IF;
END $$;

-- remove existing password policies
DELETE FROM ir_config_parameter
WHERE key LIKE 'auth_password_policy.%';

-- DATABASE CONFIGURATION ------------------------------------------------------

-- remove enterprise code
DELETE FROM ir_config_parameter
WHERE KEY = 'database.enterprise_code';

-- remove expiration date
UPDATE ir_config_parameter
SET value = '2095-12-21 00:00:00'
WHERE key = 'database.expiration_date';

-- remove existing report url
DELETE FROM ir_config_parameter
WHERE key = 'report.url';

-- set the base url to self
UPDATE ir_config_parameter
SET value = 'http://localhost:8069'
WHERE key = 'web.base.url';

-- disable push notifications
DELETE FROM ir_config_parameter
WHERE key IN (
    'ocn.ocn_push_notification',
    'odoo_ocn.project_id',
    'ocn.uuid'
);

-- CRON JOBS -------------------------------------------------------------------

-- disable crons
UPDATE ir_cron
SET active = false
WHERE id NOT IN (
    SELECT res_id
    FROM ir_model_data
    WHERE model = 'ir.cron'
        AND name = 'autovacuum_job'
);

-- MAIL SERVERS ----------------------------------------------------------------

-- disable incoming mail servers
DO $$
BEGIN
IF EXISTS (
    SELECT *
    FROM information_schema.tables
    WHERE table_name = 'fetchmail_server'
) THEN
    DELETE FROM fetchmail_server;
END IF;
END $$;

-- disable outgoing mail servers
UPDATE ir_mail_server
SET active = 'False';

-- SAAS MODULES ----------------------------------------------------------------

-- uninstall SaaS modules
UPDATE ir_module_module
SET state = 'uninstalled'
WHERE name ILIKE '%saas%';

-- remove SaaS views
DELETE FROM ir_ui_view
WHERE name ilike '%saas%';

-- WEBSITES --------------------------------------------------------------------

-- remove custom domains from websites
DO $$
BEGIN
IF EXISTS (
    SELECT *
    FROM information_schema.columns
    WHERE table_name = 'website'
        AND column_name = 'domain'
) THEN
    UPDATE website
    SET domain = NULL;
END IF;
END $$;

-- FINISHING UP ----------------------------------------------------------------

-- mark the database as neutralized
INSERT INTO ir_config_parameter (key, value)
VALUES ('database.is_neutralized', true)
    ON CONFLICT (key)
    DO UPDATE SET value = true;

-- activate neutralization watermarks
UPDATE ir_ui_view
SET active = true
WHERE key = 'web.neutralize_banner';
