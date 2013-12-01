# -*- coding: utf-8 -*-
from boto.cloudfront import CloudFrontConnection, exception
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.contrib.staticfiles.management.commands.collectstatic \
    import Command as CollectCommand
from urlparse import urljoin, urlsplit


class Command(CollectCommand):

    def handle_noargs(self, **options):
        try:
            access_key = settings.AWS_ACCESS_KEY_ID
            secret_key = settings.AWS_SECRET_ACCESS_KEY
            distribution = settings.AWS_CF_DISTRIBUTION_ID
            static_url = settings.STATIC_URL

        except AttributeError:
            raise ImproperlyConfigured(
                'Please specify AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,'
                ' AWS_CF_DISTRIBUTION_ID in settings\n')

        super(Command, self).handle_noargs(**options)

        invalid_files = self.copied_files + self.symlinked_files
        if not len(invalid_files):
            self.stdout.write('Nothing to invalidate\n')
            return

        self.stdout.write('Invalidating files...\n')
        # we need add static prefix to each address
        static_prefix = urlsplit(static_url).path
        invalid_files = \
            [urljoin(static_prefix, path) for path in invalid_files if path]

        invalidation_step = 1000
        invalication_max_num = 3
        invalidation_max_files = invalidation_step * invalication_max_num

        def dump(invalid_files):
            import tempfile
            from django.utils import simplejson
            dump = tempfile.NamedTemporaryFile(delete=False)
            dump.write(simplejson.dumps(invalid_files, indent=2))
            dump.close()
            return dump.name

        if len(invalid_files) > invalidation_max_files:
            raise AssertionError(
                "There are more than %s files to invalidate, "
                "AWS doesn't support it at the moment.\n"
                "File names to be invalidated dumped to JSON file %s, "
                "please invalidate manually\n"""
                % (invalidation_max_files, dump(invalid_files)))

        conn = CloudFrontConnection(access_key, secret_key)

        try:
            for i in xrange(invalication_max_num):
                thousand = invalid_files[i:i + invalidation_step]
                if not thousand: break
                conn.create_invalidation_request(distribution, thousand)
        except exception.CloudFrontServerError, message:
            self.stderr.write('Error while processing:\n\n%s\n\n'
                'Unprocessed files dumped to JSON file %s, '
                'please invalidate manually\n'
                % (message, dump(invalid_files)))
        else:
            self.stdout.write('Complete\n')
