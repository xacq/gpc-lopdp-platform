from django.db import migrations


FORWARD_SQL = """
ALTER TABLE "request_communications"
    DROP CONSTRAINT
    "request_communicatio_request_id_8c8f2c23_fk_rights_re";

ALTER TABLE "request_communications"
    ADD CONSTRAINT "fk_communications_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


ALTER TABLE "request_communications"
    DROP CONSTRAINT
    "request_communications_sent_by_id_31442011_fk_users_id";

ALTER TABLE "request_communications"
    ADD CONSTRAINT "fk_communications_sent_by"
    FOREIGN KEY ("sent_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;
"""


REVERSE_SQL = """
ALTER TABLE "request_communications"
    DROP CONSTRAINT "fk_communications_sent_by";

ALTER TABLE "request_communications"
    ADD CONSTRAINT
    "request_communications_sent_by_id_31442011_fk_users_id"
    FOREIGN KEY ("sent_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_communications"
    DROP CONSTRAINT "fk_communications_request";

ALTER TABLE "request_communications"
    ADD CONSTRAINT
    "request_communicatio_request_id_8c8f2c23_fk_rights_re"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "communications",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]