# Partial unique index on LOWER(auth_user.email).
#
# User.email is not unique by default and defaults to "" for users created
# without one (createsuperuser, admin-created accounts, etc). A plain
# unique index on LOWER(email) would treat every such user as a duplicate
# of every other emailless user, breaking createsuperuser after the first
# emailless account exists. The index is therefore PARTIAL — it only
# applies to rows where email <> '' — so case-insensitive email uniqueness
# is enforced for real accounts without touching emailless ones.
from django.db import migrations

CREATE_UNIQUE_LOWER_EMAIL_INDEX = """
CREATE UNIQUE INDEX uniq_auth_user_lower_email
ON auth_user (LOWER(email))
WHERE email <> '';
"""

DROP_UNIQUE_LOWER_EMAIL_INDEX = """
DROP INDEX IF EXISTS uniq_auth_user_lower_email;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_UNIQUE_LOWER_EMAIL_INDEX,
            reverse_sql=DROP_UNIQUE_LOWER_EMAIL_INDEX,
        ),
    ]
