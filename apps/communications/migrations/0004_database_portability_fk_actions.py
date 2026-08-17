from django.db import migrations


FORWARD_SQL = """
ALTER TABLE "portability_exports"
    DROP CONSTRAINT
    "portability_exports_generated_by_id_ba0f655d_fk_users_id";

ALTER TABLE "portability_exports"
    ADD CONSTRAINT "fk_portability_generated_by"
    FOREIGN KEY ("generated_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "portability_exports"
    DROP CONSTRAINT
    "portability_exports_request_id_441c0002_fk_rights_requests_id";

ALTER TABLE "portability_exports"
    ADD CONSTRAINT "fk_portability_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;
"""


REVERSE_SQL = """
ALTER TABLE "portability_exports"
    DROP CONSTRAINT "fk_portability_request";

ALTER TABLE "portability_exports"
    ADD CONSTRAINT
    "portability_exports_request_id_441c0002_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "portability_exports"
    DROP CONSTRAINT "fk_portability_generated_by";

ALTER TABLE "portability_exports"
    ADD CONSTRAINT
    "portability_exports_generated_by_id_ba0f655d_fk_users_id"
    FOREIGN KEY ("generated_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "communications",
            "0003_portabilityexport",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]