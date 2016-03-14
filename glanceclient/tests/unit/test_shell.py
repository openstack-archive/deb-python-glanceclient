# Copyright 2013 OpenStack Foundation
# Copyright (C) 2013 Yahoo! Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import argparse
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict
import hashlib
import os
import sys
import uuid

import fixtures
from keystoneclient import exceptions as ks_exc
from keystoneclient import fixture as ks_fixture
import mock
import requests
from requests_mock.contrib import fixture as rm_fixture
import six

from glanceclient.common import utils
from glanceclient import exc
from glanceclient import shell as openstack_shell
from glanceclient.tests import utils as testutils

# NOTE (esheffield) Used for the schema caching tests
from glanceclient.v2 import schemas as schemas
import json


DEFAULT_IMAGE_URL = 'http://127.0.0.1:5000/'
DEFAULT_USERNAME = 'username'
DEFAULT_PASSWORD = 'password'
DEFAULT_TENANT_ID = 'tenant_id'
DEFAULT_TENANT_NAME = 'tenant_name'
DEFAULT_PROJECT_ID = '0123456789'
DEFAULT_USER_DOMAIN_NAME = 'user_domain_name'
DEFAULT_UNVERSIONED_AUTH_URL = 'http://127.0.0.1:5000/'
DEFAULT_V2_AUTH_URL = '%sv2.0' % DEFAULT_UNVERSIONED_AUTH_URL
DEFAULT_V3_AUTH_URL = '%sv3' % DEFAULT_UNVERSIONED_AUTH_URL
DEFAULT_AUTH_TOKEN = ' 3bcc3d3a03f44e3d8377f9247b0ad155'
TEST_SERVICE_URL = 'http://127.0.0.1:5000/'

FAKE_V2_ENV = {'OS_USERNAME': DEFAULT_USERNAME,
               'OS_PASSWORD': DEFAULT_PASSWORD,
               'OS_TENANT_NAME': DEFAULT_TENANT_NAME,
               'OS_AUTH_URL': DEFAULT_V2_AUTH_URL,
               'OS_IMAGE_URL': DEFAULT_IMAGE_URL}

FAKE_V3_ENV = {'OS_USERNAME': DEFAULT_USERNAME,
               'OS_PASSWORD': DEFAULT_PASSWORD,
               'OS_PROJECT_ID': DEFAULT_PROJECT_ID,
               'OS_USER_DOMAIN_NAME': DEFAULT_USER_DOMAIN_NAME,
               'OS_AUTH_URL': DEFAULT_V3_AUTH_URL,
               'OS_IMAGE_URL': DEFAULT_IMAGE_URL}

TOKEN_ID = uuid.uuid4().hex

V2_TOKEN = ks_fixture.V2Token(token_id=TOKEN_ID)
V2_TOKEN.set_scope()
_s = V2_TOKEN.add_service('image', name='glance')
_s.add_endpoint(DEFAULT_IMAGE_URL)

V3_TOKEN = ks_fixture.V3Token()
V3_TOKEN.set_project_scope()
_s = V3_TOKEN.add_service('image', name='glance')
_s.add_standard_endpoints(public=DEFAULT_IMAGE_URL)


class ShellTest(testutils.TestCase):
    # auth environment to use
    auth_env = FAKE_V2_ENV.copy()
    # expected auth plugin to invoke
    token_url = DEFAULT_V2_AUTH_URL + '/tokens'

    # Patch os.environ to avoid required auth info
    def make_env(self, exclude=None):
        env = dict((k, v) for k, v in self.auth_env.items() if k != exclude)
        self.useFixture(fixtures.MonkeyPatch('os.environ', env))

    def setUp(self):
        super(ShellTest, self).setUp()
        global _old_env
        _old_env, os.environ = os.environ, self.auth_env

        self.requests = self.useFixture(rm_fixture.Fixture())

        json_list = ks_fixture.DiscoveryList(DEFAULT_UNVERSIONED_AUTH_URL)
        self.requests.get(DEFAULT_IMAGE_URL, json=json_list, status_code=300)

        json_v2 = {'version': ks_fixture.V2Discovery(DEFAULT_V2_AUTH_URL)}
        self.requests.get(DEFAULT_V2_AUTH_URL, json=json_v2)

        json_v3 = {'version': ks_fixture.V3Discovery(DEFAULT_V3_AUTH_URL)}
        self.requests.get(DEFAULT_V3_AUTH_URL, json=json_v3)

        self.v2_auth = self.requests.post(DEFAULT_V2_AUTH_URL + '/tokens',
                                          json=V2_TOKEN)

        headers = {'X-Subject-Token': TOKEN_ID}
        self.v3_auth = self.requests.post(DEFAULT_V3_AUTH_URL + '/auth/tokens',
                                          headers=headers,
                                          json=V3_TOKEN)

        global shell, _shell, assert_called, assert_called_anytime
        _shell = openstack_shell.OpenStackImagesShell()
        shell = lambda cmd: _shell.main(cmd.split())

    def tearDown(self):
        super(ShellTest, self).tearDown()
        global _old_env
        os.environ = _old_env

    def shell(self, argstr, exitcodes=(0,)):
        orig = sys.stdout
        orig_stderr = sys.stderr
        try:
            sys.stdout = six.StringIO()
            sys.stderr = six.StringIO()
            _shell = openstack_shell.OpenStackImagesShell()
            _shell.main(argstr.split())
        except SystemExit:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.assertIn(exc_value.code, exitcodes)
        finally:
            stdout = sys.stdout.getvalue()
            sys.stdout.close()
            sys.stdout = orig
            stderr = sys.stderr.getvalue()
            sys.stderr.close()
            sys.stderr = orig_stderr
        return (stdout, stderr)

    def test_help_unknown_command(self):
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 2 help foofoo'
        self.assertRaises(exc.CommandError, shell.main, argstr.split())

    def test_help(self):
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 2 help'
        with mock.patch.object(shell, '_get_keystone_session') as et_mock:
            actual = shell.main(argstr.split())
            self.assertEqual(0, actual)
            self.assertFalse(et_mock.called)

    def test_blank_call(self):
        shell = openstack_shell.OpenStackImagesShell()
        with mock.patch.object(shell, '_get_keystone_session') as et_mock:
            actual = shell.main('')
            self.assertEqual(0, actual)
            self.assertFalse(et_mock.called)

    def test_help_on_subcommand_error(self):
        self.assertRaises(exc.CommandError, shell,
                          '--os-image-api-version 2 help bad')

    def test_help_v2_no_schema(self):
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 2 help image-create'
        with mock.patch.object(shell, '_get_keystone_session') as et_mock:
            actual = shell.main(argstr.split())
            self.assertEqual(0, actual)
            self.assertNotIn('<unavailable>', actual)
            self.assertFalse(et_mock.called)

    def test_get_base_parser(self):
        test_shell = openstack_shell.OpenStackImagesShell()
        actual_parser = test_shell.get_base_parser()
        description = 'Command-line interface to the OpenStack Images API.'
        expected = argparse.ArgumentParser(
            prog='glance', usage=None,
            description=description,
            conflict_handler='error',
            add_help=False,
            formatter_class=openstack_shell.HelpFormatter,)
        # NOTE(guochbo): Can't compare ArgumentParser instances directly
        # Convert ArgumentPaser to string first.
        self.assertEqual(str(expected), str(actual_parser))

    @mock.patch.object(openstack_shell.OpenStackImagesShell,
                       '_get_versioned_client')
    def test_cert_and_key_args_interchangeable(self,
                                               mock_versioned_client):
        # make sure --os-cert and --os-key are passed correctly
        args = ('--os-image-api-version 2 '
                '--os-cert mycert '
                '--os-key mykey image-list')
        shell(args)
        assert mock_versioned_client.called
        ((api_version, args), kwargs) = mock_versioned_client.call_args
        self.assertEqual('mycert', args.os_cert)
        self.assertEqual('mykey', args.os_key)

        # make sure we get the same thing with --cert-file and --key-file
        args = ('--os-image-api-version 2 '
                '--cert-file mycertfile '
                '--key-file mykeyfile image-list')
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        assert mock_versioned_client.called
        ((api_version, args), kwargs) = mock_versioned_client.call_args
        self.assertEqual('mycertfile', args.os_cert)
        self.assertEqual('mykeyfile', args.os_key)

    @mock.patch('glanceclient.v1.client.Client')
    def test_no_auth_with_token_and_image_url_with_v1(self, v1_client):
        # test no authentication is required if both token and endpoint url
        # are specified
        args = ('--os-image-api-version 1 --os-auth-token mytoken'
                ' --os-image-url https://image:1234/v1 image-list')
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        assert v1_client.called
        (args, kwargs) = v1_client.call_args
        self.assertEqual('mytoken', kwargs['token'])
        self.assertEqual('https://image:1234', args[0])

    @mock.patch('glanceclient.v2.client.Client')
    def test_no_auth_with_token_and_image_url_with_v2(self, v2_client):
        # test no authentication is required if both token and endpoint url
        # are specified
        args = ('--os-image-api-version 2 --os-auth-token mytoken '
                '--os-image-url https://image:1234 image-list')
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertTrue(v2_client.called)
        (args, kwargs) = v2_client.call_args
        self.assertEqual('mytoken', kwargs['token'])
        self.assertEqual('https://image:1234', args[0])

    def _assert_auth_plugin_args(self):
        # make sure our auth plugin is invoked with the correct args
        self.assertFalse(self.v3_auth.called)

        body = json.loads(self.v2_auth.last_request.body)

        self.assertEqual(self.auth_env['OS_TENANT_NAME'],
                         body['auth']['tenantName'])
        self.assertEqual(self.auth_env['OS_USERNAME'],
                         body['auth']['passwordCredentials']['username'])
        self.assertEqual(self.auth_env['OS_PASSWORD'],
                         body['auth']['passwordCredentials']['password'])

    @mock.patch.object(openstack_shell.OpenStackImagesShell, '_cache_schemas',
                       return_value=False)
    @mock.patch('glanceclient.v2.client.Client')
    def test_auth_plugin_invocation_without_version(self,
                                                    v2_client,
                                                    cache_schemas):

        cli2 = mock.MagicMock()
        v2_client.return_value = cli2
        cli2.http_client.get.return_value = (None, {'versions':
                                                    [{'id': 'v2'}]})

        args = 'image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        # NOTE(flaper87): this currently calls auth twice since it'll
        # authenticate to get the version list *and* to execute the command.
        # This is not the ideal behavior and it should be fixed in a follow
        # up patch.

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_with_v1(self, v1_client):
        args = '--os-image-api-version 1 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertEqual(0, self.v2_auth.call_count)

    @mock.patch('glanceclient.v2.client.Client')
    def test_auth_plugin_invocation_with_v2(self,
                                            v2_client):
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertEqual(0, self.v2_auth.call_count)

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_with_unversioned_auth_url_with_v1(
            self, v1_client):
        args = ('--os-image-api-version 1 --os-auth-url %s image-list' %
                DEFAULT_UNVERSIONED_AUTH_URL)
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())

    @mock.patch('glanceclient.v2.client.Client')
    @mock.patch.object(openstack_shell.OpenStackImagesShell, '_cache_schemas',
                       return_value=False)
    def test_auth_plugin_invocation_with_unversioned_auth_url_with_v2(
            self, v2_client, cache_schemas):
        args = ('--os-auth-url %s --os-image-api-version 2 '
                'image-list') % DEFAULT_UNVERSIONED_AUTH_URL
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())

    @mock.patch('glanceclient.Client')
    def test_endpoint_token_no_auth_req(self, mock_client):

        def verify_input(version=None, endpoint=None, *args, **kwargs):
            self.assertIn('token', kwargs)
            self.assertEqual(TOKEN_ID, kwargs['token'])
            self.assertEqual(DEFAULT_IMAGE_URL, endpoint)
            return mock.MagicMock()

        mock_client.side_effect = verify_input
        glance_shell = openstack_shell.OpenStackImagesShell()
        args = ['--os-image-api-version', '2',
                '--os-auth-token', TOKEN_ID,
                '--os-image-url', DEFAULT_IMAGE_URL,
                'image-list']

        glance_shell.main(args)
        self.assertEqual(1, mock_client.call_count)

    @mock.patch('glanceclient.v2.client.Client')
    def test_password_prompted_with_v2(self, v2_client):
        self.requests.post(self.token_url, exc=requests.ConnectionError)

        cli2 = mock.MagicMock()
        v2_client.return_value = cli2
        cli2.http_client.get.return_value = (None, {'versions': []})
        glance_shell = openstack_shell.OpenStackImagesShell()
        os.environ['OS_PASSWORD'] = 'password'
        self.assertRaises(exc.CommunicationError,
                          glance_shell.main, ['image-list'])

    @mock.patch('sys.stdin', side_effect=mock.MagicMock)
    @mock.patch('getpass.getpass', side_effect=EOFError)
    @mock.patch('glanceclient.v2.client.Client')
    def test_password_prompted_ctrlD_with_v2(self, v2_client,
                                             mock_getpass, mock_stdin):
        cli2 = mock.MagicMock()
        v2_client.return_value = cli2
        cli2.http_client.get.return_value = (None, {'versions': []})

        glance_shell = openstack_shell.OpenStackImagesShell()
        self.make_env(exclude='OS_PASSWORD')
        # We should get Command Error because we mock Ctl-D.
        self.assertRaises(exc.CommandError, glance_shell.main, ['image-list'])
        # Make sure we are actually prompted.
        mock_getpass.assert_called_with('OS Password: ')

    @mock.patch(
        'glanceclient.shell.OpenStackImagesShell._get_keystone_session')
    @mock.patch.object(openstack_shell.OpenStackImagesShell, '_cache_schemas',
                       return_value=False)
    def test_no_auth_with_proj_name(self, cache_schemas, session):
        with mock.patch('glanceclient.v2.client.Client'):
            args = ('--os-project-name myname '
                    '--os-project-domain-name mydomain '
                    '--os-project-domain-id myid '
                    '--os-image-api-version 2 image-list')
            glance_shell = openstack_shell.OpenStackImagesShell()
            glance_shell.main(args.split())
            ((args), kwargs) = session.call_args
            self.assertEqual('myname', kwargs['project_name'])
            self.assertEqual('mydomain', kwargs['project_domain_name'])
            self.assertEqual('myid', kwargs['project_domain_id'])

    @mock.patch.object(openstack_shell.OpenStackImagesShell, 'main')
    def test_shell_keyboard_interrupt(self, mock_glance_shell):
        # Ensure that exit code is 130 for KeyboardInterrupt
        try:
            mock_glance_shell.side_effect = KeyboardInterrupt()
            openstack_shell.main()
        except SystemExit as ex:
            self.assertEqual(130, ex.code)

    @mock.patch('glanceclient.common.utils.exit', side_effect=utils.exit)
    def test_shell_illegal_version(self, mock_exit):
        # Only int versions are allowed on cli
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 1.1 image-list'
        try:
            shell.main(argstr.split())
        except SystemExit as ex:
            self.assertEqual(1, ex.code)
        msg = ("Invalid API version parameter. "
               "Supported values are %s" % openstack_shell.SUPPORTED_VERSIONS)
        mock_exit.assert_called_with(msg=msg)

    @mock.patch('glanceclient.common.utils.exit', side_effect=utils.exit)
    def test_shell_unsupported_version(self, mock_exit):
        # Test an integer version which is not supported (-1)
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version -1 image-list'
        try:
            shell.main(argstr.split())
        except SystemExit as ex:
            self.assertEqual(1, ex.code)
        msg = ("Invalid API version parameter. "
               "Supported values are %s" % openstack_shell.SUPPORTED_VERSIONS)
        mock_exit.assert_called_with(msg=msg)

    @mock.patch.object(openstack_shell.OpenStackImagesShell,
                       'get_subcommand_parser')
    def test_shell_import_error_with_mesage(self, mock_parser):
        msg = 'Unable to import module xxx'
        mock_parser.side_effect = ImportError('%s' % msg)
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 2 image-list'
        try:
            shell.main(argstr.split())
            self.fail('No import error returned')
        except ImportError as e:
            self.assertEqual(msg, str(e))

    @mock.patch.object(openstack_shell.OpenStackImagesShell,
                       'get_subcommand_parser')
    def test_shell_import_error_default_message(self, mock_parser):
        mock_parser.side_effect = ImportError
        shell = openstack_shell.OpenStackImagesShell()
        argstr = '--os-image-api-version 2 image-list'
        try:
            shell.main(argstr.split())
            self.fail('No import error returned')
        except ImportError as e:
            msg = 'Unable to import module. Re-run with --debug for more info.'
            self.assertEqual(msg, str(e))

    @mock.patch('glanceclient.v2.client.Client')
    @mock.patch('glanceclient.v1.images.ImageManager.list')
    def test_shell_v1_fallback_from_v2(self, v1_imgs, v2_client):
        self.make_env()
        cli2 = mock.MagicMock()
        v2_client.return_value = cli2
        cli2.http_client.get.return_value = (None, {'versions': []})
        args = 'image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertFalse(cli2.schemas.get.called)
        self.assertTrue(v1_imgs.called)

    @mock.patch.object(openstack_shell.OpenStackImagesShell,
                       '_cache_schemas')
    @mock.patch('glanceclient.v2.client.Client')
    def test_shell_no_fallback_from_v2(self, v2_client, cache_schemas):
        self.make_env()
        cli2 = mock.MagicMock()
        v2_client.return_value = cli2
        cli2.http_client.get.return_value = (None,
                                             {'versions': [{'id': 'v2'}]})
        cache_schemas.return_value = False
        args = 'image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertTrue(cli2.images.list.called)

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_without_username_with_v1(self, v1_client):
        self.make_env(exclude='OS_USERNAME')
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('glanceclient.v2.client.Client')
    def test_auth_plugin_invocation_without_username_with_v2(self, v2_client):
        self.make_env(exclude='OS_USERNAME')
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_without_auth_url_with_v1(self, v1_client):
        self.make_env(exclude='OS_AUTH_URL')
        args = '--os-image-api-version 1 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('glanceclient.v2.client.Client')
    def test_auth_plugin_invocation_without_auth_url_with_v2(self, v2_client):
        self.make_env(exclude='OS_AUTH_URL')
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_without_tenant_with_v1(self, v1_client):
        if 'OS_TENANT_NAME' in os.environ:
            self.make_env(exclude='OS_TENANT_NAME')
        if 'OS_PROJECT_ID' in os.environ:
            self.make_env(exclude='OS_PROJECT_ID')
        args = '--os-image-api-version 1 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('glanceclient.v2.client.Client')
    @mock.patch.object(openstack_shell.OpenStackImagesShell, '_cache_schemas',
                       return_value=False)
    def test_auth_plugin_invocation_without_tenant_with_v2(self, v2_client,
                                                           cache_schemas):
        if 'OS_TENANT_NAME' in os.environ:
            self.make_env(exclude='OS_TENANT_NAME')
        if 'OS_PROJECT_ID' in os.environ:
            self.make_env(exclude='OS_PROJECT_ID')
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    @mock.patch('sys.argv', ['glance'])
    @mock.patch('sys.stdout', six.StringIO())
    @mock.patch('sys.stderr', six.StringIO())
    def test_main_noargs(self):
        # Ensure that main works with no command-line arguments
        try:
            openstack_shell.main()
        except SystemExit:
            self.fail('Unexpected SystemExit')

        # We expect the normal usage as a result
        self.assertIn('Command-line interface to the OpenStack Images API',
                      sys.stdout.getvalue())


class ShellTestWithKeystoneV3Auth(ShellTest):
    # auth environment to use
    auth_env = FAKE_V3_ENV.copy()
    token_url = DEFAULT_V3_AUTH_URL + '/auth/tokens'

    def _assert_auth_plugin_args(self):
        self.assertFalse(self.v2_auth.called)

        body = json.loads(self.v3_auth.last_request.body)
        user = body['auth']['identity']['password']['user']

        self.assertEqual(self.auth_env['OS_USERNAME'], user['name'])
        self.assertEqual(self.auth_env['OS_PASSWORD'], user['password'])
        self.assertEqual(self.auth_env['OS_USER_DOMAIN_NAME'],
                         user['domain']['name'])
        self.assertEqual(self.auth_env['OS_PROJECT_ID'],
                         body['auth']['scope']['project']['id'])

    @mock.patch('glanceclient.v1.client.Client')
    def test_auth_plugin_invocation_with_v1(self, v1_client):
        args = '--os-image-api-version 1 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertEqual(0, self.v3_auth.call_count)

    @mock.patch('glanceclient.v2.client.Client')
    def test_auth_plugin_invocation_with_v2(self, v2_client):
        args = '--os-image-api-version 2 image-list'
        glance_shell = openstack_shell.OpenStackImagesShell()
        glance_shell.main(args.split())
        self.assertEqual(0, self.v3_auth.call_count)

    @mock.patch('keystoneclient.discover.Discover',
                side_effect=ks_exc.ClientException())
    def test_api_discovery_failed_with_unversioned_auth_url(self,
                                                            discover):
        args = ('--os-image-api-version 2 --os-auth-url %s image-list'
                % DEFAULT_UNVERSIONED_AUTH_URL)
        glance_shell = openstack_shell.OpenStackImagesShell()
        self.assertRaises(exc.CommandError, glance_shell.main, args.split())

    def test_bash_completion(self):
        stdout, stderr = self.shell('--os-image-api-version 2 bash_completion')
        # just check we have some output
        required = [
            '--status',
            'image-create',
            'help',
            '--size']
        for r in required:
            self.assertIn(r, stdout.split())
        avoided = [
            'bash_completion',
            'bash-completion']
        for r in avoided:
            self.assertNotIn(r, stdout.split())


class ShellCacheSchemaTest(testutils.TestCase):
    def setUp(self):
        super(ShellCacheSchemaTest, self).setUp()
        self._mock_client_setup()
        self._mock_shell_setup()
        self.cache_dir = '/dir_for_cached_schema'
        self.os_auth_url = 'http://localhost:5000/v2'
        url_hex = hashlib.sha1(self.os_auth_url.encode('utf-8')).hexdigest()
        self.prefix_path = (self.cache_dir + '/' + url_hex)
        self.cache_files = [self.prefix_path + '/image_schema.json',
                            self.prefix_path + '/namespace_schema.json',
                            self.prefix_path + '/resource_type_schema.json']

    def tearDown(self):
        super(ShellCacheSchemaTest, self).tearDown()

    def _mock_client_setup(self):
        self.schema_dict = {
            'name': 'image',
            'properties': {
                'name': {'type': 'string', 'description': 'Name of image'},
            },
        }

        self.client = mock.Mock()
        schema_odict = OrderedDict(self.schema_dict)
        self.client.schemas.get.return_value = schemas.Schema(schema_odict)

    def _mock_shell_setup(self):
        self.shell = openstack_shell.OpenStackImagesShell()
        self.shell._get_versioned_client = mock.create_autospec(
            self.shell._get_versioned_client, return_value=self.client,
            spec_set=True
        )

    def _make_args(self, args):
        class Args(object):
            def __init__(self, entries):
                self.__dict__.update(entries)

        return Args(args)

    @mock.patch('six.moves.builtins.open', new=mock.mock_open(), create=True)
    @mock.patch('os.path.exists', return_value=True)
    def test_cache_schemas_gets_when_forced(self, exists_mock):
        options = {
            'get_schema': True,
            'os_auth_url': self.os_auth_url
        }
        schema_odict = OrderedDict(self.schema_dict)

        args = self._make_args(options)
        client = self.shell._get_versioned_client('2', args)
        self.shell._cache_schemas(args, client, home_dir=self.cache_dir)

        self.assertEqual(12, open.mock_calls.__len__())
        self.assertEqual(mock.call(self.cache_files[0], 'w'),
                         open.mock_calls[0])
        self.assertEqual(mock.call(self.cache_files[1], 'w'),
                         open.mock_calls[4])
        self.assertEqual(mock.call().write(json.dumps(schema_odict)),
                         open.mock_calls[2])
        self.assertEqual(mock.call().write(json.dumps(schema_odict)),
                         open.mock_calls[6])

    @mock.patch('six.moves.builtins.open', new=mock.mock_open(), create=True)
    @mock.patch('os.path.exists', side_effect=[True, False, False, False])
    def test_cache_schemas_gets_when_not_exists(self, exists_mock):
        options = {
            'get_schema': False,
            'os_auth_url': self.os_auth_url
        }
        schema_odict = OrderedDict(self.schema_dict)

        args = self._make_args(options)
        client = self.shell._get_versioned_client('2', args)
        self.shell._cache_schemas(args, client, home_dir=self.cache_dir)

        self.assertEqual(12, open.mock_calls.__len__())
        self.assertEqual(mock.call(self.cache_files[0], 'w'),
                         open.mock_calls[0])
        self.assertEqual(mock.call(self.cache_files[1], 'w'),
                         open.mock_calls[4])
        self.assertEqual(mock.call().write(json.dumps(schema_odict)),
                         open.mock_calls[2])
        self.assertEqual(mock.call().write(json.dumps(schema_odict)),
                         open.mock_calls[6])

    @mock.patch('six.moves.builtins.open', new=mock.mock_open(), create=True)
    @mock.patch('os.path.exists', return_value=True)
    def test_cache_schemas_leaves_when_present_not_forced(self, exists_mock):
        options = {
            'get_schema': False,
            'os_auth_url': self.os_auth_url
        }

        client = mock.MagicMock()
        self.shell._cache_schemas(self._make_args(options),
                                  client, home_dir=self.cache_dir)

        exists_mock.assert_has_calls([
            mock.call(self.prefix_path),
            mock.call(self.cache_files[0]),
            mock.call(self.cache_files[1]),
            mock.call(self.cache_files[2])
        ])
        self.assertEqual(4, exists_mock.call_count)
        self.assertEqual(0, open.mock_calls.__len__())

    @mock.patch('six.moves.builtins.open', new=mock.mock_open(), create=True)
    @mock.patch('os.path.exists', return_value=True)
    def test_cache_schemas_leaves_auto_switch(self, exists_mock):
        options = {
            'get_schema': True,
            'os_auth_url': self.os_auth_url
        }

        self.client.schemas.get.return_value = Exception()

        client = mock.MagicMock()
        switch_version = self.shell._cache_schemas(self._make_args(options),
                                                   client,
                                                   home_dir=self.cache_dir)
        self.assertEqual(switch_version, True)
