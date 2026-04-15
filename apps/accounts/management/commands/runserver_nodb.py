from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    help = "Run the development server without the startup migration database check."

    def check_migrations(self):
        # The default runserver command opens a database connection here.
        # This project uses a remote Supabase/Postgres database, so skipping
        # the startup migration check keeps local boot from failing when the
        # database is temporarily unreachable.
        return
