#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    if 'test' in sys.argv:
        # Tests must not require a running Redis: force the LocMemCache
        # branch in settings.py regardless of what's in .env. Dedicated
        # throttle tests (Phase 3b) override CACHES back to Redis themselves
        # and skip if it's unreachable.
        os.environ.setdefault('DJANGO_TESTING', 'True')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
