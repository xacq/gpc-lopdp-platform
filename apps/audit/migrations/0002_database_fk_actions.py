from django.db import migrations


FORWARD_SQL = """
ALTER TABLE "audit_logs"
    DROP CONSTRAINT
    "audit_logs_actor_user_id_01017f5b_fk_users_id";

ALTER TABLE "audit_logs"
    ADD CONSTRAINT "fk_audit_actor_user"
    FOREIGN KEY ("actor_user_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;
"""


REVERSE_SQL = """
ALTER TABLE "audit_logs"
    DROP CONSTRAINT "fk_audit_actor_user";

ALTER TABLE "audit_logs"
    ADD CONSTRAINT
    "audit_logs_actor_user_id_01017f5b_fk_users_id"
    FOREIGN KEY ("actor_user_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "audit",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]