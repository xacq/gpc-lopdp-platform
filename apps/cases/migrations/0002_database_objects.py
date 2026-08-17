from django.db import migrations


FORWARD_SQL = """
CREATE SEQUENCE rights_request_seq
    AS BIGINT
    START WITH 1
    INCREMENT BY 1;


-- ============================================================
-- RIGHTS REQUESTS
-- ============================================================

ALTER TABLE "rights_requests"
    DROP CONSTRAINT
    "rights_requests_assigned_to_id_41d03d94_fk_users_id";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT "fk_rights_requests_assigned_to"
    FOREIGN KEY ("assigned_to_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "rights_requests"
    DROP CONSTRAINT
    "rights_requests_data_subject_id_9726102f_fk_data_subjects_id";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT "fk_rights_requests_subject"
    FOREIGN KEY ("data_subject_id")
    REFERENCES "data_subjects" ("id")
    ON DELETE RESTRICT;


ALTER TABLE "rights_requests"
    DROP CONSTRAINT
    "rights_requests_right_id_2272cdca_fk_rights_catalog_id";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT "fk_rights_requests_right"
    FOREIGN KEY ("right_id")
    REFERENCES "rights_catalog" ("id")
    ON DELETE RESTRICT;


-- Garantiza que el representante pertenezca al mismo titular.
ALTER TABLE "rights_requests"
    ADD CONSTRAINT "fk_request_representative_same_subject"
    FOREIGN KEY ("representative_id", "data_subject_id")
    REFERENCES "subject_representatives" ("id", "data_subject_id")
    ON DELETE RESTRICT;


-- ============================================================
-- STATUS HISTORY
-- ============================================================

ALTER TABLE "request_status_history"
    DROP CONSTRAINT
    "request_status_history_changed_by_id_30d36960_fk_users_id";

ALTER TABLE "request_status_history"
    ADD CONSTRAINT "fk_status_history_changed_by"
    FOREIGN KEY ("changed_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "request_status_history"
    DROP CONSTRAINT
    "request_status_histo_request_id_401d2817_fk_rights_re";

ALTER TABLE "request_status_history"
    ADD CONSTRAINT "fk_status_history_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


-- ============================================================
-- DEADLINES
-- ============================================================

ALTER TABLE "request_deadlines"
    DROP CONSTRAINT
    "request_deadlines_request_id_d02d308b_fk_rights_requests_id";

ALTER TABLE "request_deadlines"
    ADD CONSTRAINT "fk_deadlines_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


-- ============================================================
-- CLARIFICATIONS
-- ============================================================

ALTER TABLE "request_clarifications"
    DROP CONSTRAINT
    "request_clarifications_created_by_id_96bddd84_fk_users_id";

ALTER TABLE "request_clarifications"
    ADD CONSTRAINT "fk_clarifications_created_by"
    FOREIGN KEY ("created_by_id")
    REFERENCES "users" ("id")
    ON DELETE SET NULL;


ALTER TABLE "request_clarifications"
    DROP CONSTRAINT
    "request_clarificatio_request_id_d3677266_fk_rights_re";

ALTER TABLE "request_clarifications"
    ADD CONSTRAINT "fk_clarifications_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;


-- ============================================================
-- ACCESS TOKENS
-- ============================================================

ALTER TABLE "request_access_tokens"
    DROP CONSTRAINT
    "request_access_tokens_request_id_0fd967f8_fk_rights_requests_id";

ALTER TABLE "request_access_tokens"
    ADD CONSTRAINT "fk_access_tokens_request"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    ON DELETE CASCADE;
"""


REVERSE_SQL = """
-- ============================================================
-- ACCESS TOKENS
-- ============================================================

ALTER TABLE "request_access_tokens"
    DROP CONSTRAINT "fk_access_tokens_request";

ALTER TABLE "request_access_tokens"
    ADD CONSTRAINT
    "request_access_tokens_request_id_0fd967f8_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- CLARIFICATIONS
-- ============================================================

ALTER TABLE "request_clarifications"
    DROP CONSTRAINT "fk_clarifications_request";

ALTER TABLE "request_clarifications"
    ADD CONSTRAINT
    "request_clarificatio_request_id_d3677266_fk_rights_re"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_clarifications"
    DROP CONSTRAINT "fk_clarifications_created_by";

ALTER TABLE "request_clarifications"
    ADD CONSTRAINT
    "request_clarifications_created_by_id_96bddd84_fk_users_id"
    FOREIGN KEY ("created_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- DEADLINES
-- ============================================================

ALTER TABLE "request_deadlines"
    DROP CONSTRAINT "fk_deadlines_request";

ALTER TABLE "request_deadlines"
    ADD CONSTRAINT
    "request_deadlines_request_id_d02d308b_fk_rights_requests_id"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- STATUS HISTORY
-- ============================================================

ALTER TABLE "request_status_history"
    DROP CONSTRAINT "fk_status_history_request";

ALTER TABLE "request_status_history"
    ADD CONSTRAINT
    "request_status_histo_request_id_401d2817_fk_rights_re"
    FOREIGN KEY ("request_id")
    REFERENCES "rights_requests" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "request_status_history"
    DROP CONSTRAINT "fk_status_history_changed_by";

ALTER TABLE "request_status_history"
    ADD CONSTRAINT
    "request_status_history_changed_by_id_30d36960_fk_users_id"
    FOREIGN KEY ("changed_by_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


-- ============================================================
-- RIGHTS REQUESTS
-- ============================================================

ALTER TABLE "rights_requests"
    DROP CONSTRAINT "fk_request_representative_same_subject";


ALTER TABLE "rights_requests"
    DROP CONSTRAINT "fk_rights_requests_right";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT
    "rights_requests_right_id_2272cdca_fk_rights_catalog_id"
    FOREIGN KEY ("right_id")
    REFERENCES "rights_catalog" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "rights_requests"
    DROP CONSTRAINT "fk_rights_requests_subject";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT
    "rights_requests_data_subject_id_9726102f_fk_data_subjects_id"
    FOREIGN KEY ("data_subject_id")
    REFERENCES "data_subjects" ("id")
    DEFERRABLE INITIALLY DEFERRED;


ALTER TABLE "rights_requests"
    DROP CONSTRAINT "fk_rights_requests_assigned_to";

ALTER TABLE "rights_requests"
    ADD CONSTRAINT
    "rights_requests_assigned_to_id_41d03d94_fk_users_id"
    FOREIGN KEY ("assigned_to_id")
    REFERENCES "users" ("id")
    DEFERRABLE INITIALLY DEFERRED;


DROP SEQUENCE rights_request_seq;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "cases",
            "0001_initial",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]