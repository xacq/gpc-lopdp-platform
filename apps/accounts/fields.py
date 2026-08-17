from django.db import models


class CIEmailField(models.EmailField):
    """
    EmailField backed by PostgreSQL CITEXT.

    VINESA PostgreSQL 18 Blueprint v1.5 requires users.email
    to use the CITEXT data type.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)