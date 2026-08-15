from django.db import models


class CITextField(models.TextField):
    """
    PostgreSQL CITEXT-backed text field.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)


class CIEmailField(models.EmailField):
    """
    EmailField backed by PostgreSQL CITEXT.
    """

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return "citext"

        return super().db_type(connection)