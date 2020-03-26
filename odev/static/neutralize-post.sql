-- -----------------------------------------------------------------------------
-- PS-Tech curated script to neutralize a database and making it suitable for
-- custom developments.
--
-- This script runs *after* all standard scripts.
-- -----------------------------------------------------------------------------

-- MAIL SERVERS ----------------------------------------------------------------

-- enable MailHog server
DO $$
DECLARE
    server_name VARCHAR := 'Mail Catcher';
    server_host VARCHAR := 'localhost';
    server_port INTEGER := 1025;
    server_encryption VARCHAR := 'none';
    server_authentication VARCHAR := 'login';
    server_active BOOLEAN := true;
BEGIN
IF EXISTS (
    SELECT *
    FROM information_schema.columns
    WHERE table_name = 'ir_mail_server'
        AND column_name = 'smtp_authentication'
) THEN
    INSERT INTO ir_mail_server (
        name,
        smtp_host,
        smtp_port,
        smtp_encryption,
        smtp_authentication,
        active
    )
    VALUES (
        server_name,
        server_host,
        server_port,
        server_encryption,
        server_authentication,
        server_active
    );
ELSE
    INSERT INTO ir_mail_server (
        name,
        smtp_host,
        smtp_port,
        smtp_encryption,
        active
    )
    VALUES (
        server_name,
        server_host,
        server_port,
        server_encryption,
        server_active
    );
END IF;
END $$;
