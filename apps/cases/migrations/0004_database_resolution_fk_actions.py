from django.db import migrations


FORWARD_SQL = """
-- ============================================================
-- REQUEST RESOLUTIONS
-- ============================================================

ALTER TABLE "request_resolutions"
    DROP CONSTRAINT
    "request_resolutions_outcome_reason_id_1ee0ba08_fk_case_outc";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT "fk_resolutions_outcome_reason"
    FOREIGN KEY ("outcome_reason_id")
    REFERENCES "case_outcome_reasons" ("id")
    ON DELETE RESTRICT;


ALTER TABLE "request_resolutions"
    DROP CONSTRAINT
    "request_resolutions_request_id_6a15762c_fk_rights_requests_id";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT "fk_resolutions_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


ALTER TABLE "request_resolutions"
    DROP CONSTRAINT
    "request_resolutions_resolved_by_id_6edaec94_fk_users_id";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT "fk_resolutions_resolved_by"
    FOREIGN KEY ("resolved_by_id")
    REFERENCES "users" ("id")
    ON DELETE RESTRICT;
"""


REVERSE_SQL = """
ALTER TABLE "request_resolutions"
    DROP CONSTRAINT "fk_resolutions_resolved_by";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT
    "request_resolutions_resolved_by_id_6edaec94_fk_users_id"
    FOREIGN KEY ("resolved_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_resolutions"
    DROP CONSTRAINT "fk_resolutions_request";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT
    "request_resolutions_request_id_6a15762c_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_resolutions"
    DROP CONSTRAINT "fk_resolutions_outcome_reason";

ALTER TABLE "request_resolutions"
    ADD CONSTRAINT
    "request_resolutions_outcome_reason_id_1ee0ba08_fk_case_outc"
    FOREIGN KEY ("outcome_reason_id")
    REFERENCES "case_outcome_reasons" ("id")
    DEFERRABLE INITIALLY DEFERRED;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "cases",
            "0003_caseoutcomereason_requestresolution",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]