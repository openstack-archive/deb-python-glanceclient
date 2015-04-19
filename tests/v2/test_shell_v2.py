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
import json
import mock
import os
import tempfile
import testtools

from glanceclient.common import utils
from glanceclient.v2 import shell as test_shell


class ShellV2Test(testtools.TestCase):
    def setUp(self):
        super(ShellV2Test, self).setUp()
        self._mock_utils()
        self.gc = self._mock_glance_client()

    def _make_args(self, args):
        #NOTE(venkatesh): this conversion from a dict to an object
        # is required because the test_shell.do_xxx(gc, args) methods
        # expects the args to be attributes of an object. If passed as
        # dict directly, it throws an AttributeError.
        class Args():
            def __init__(self, entries):
                self.__dict__.update(entries)

        return Args(args)

    def _mock_glance_client(self):
        my_mocked_gc = mock.Mock()
        my_mocked_gc.schemas.return_value = 'test'
        my_mocked_gc.get.return_value = {}
        return my_mocked_gc

    def _mock_utils(self):
        utils.print_list = mock.Mock()
        utils.print_dict = mock.Mock()
        utils.save_image = mock.Mock()

    def assert_exits_with_msg(self, func, func_args, err_msg):
        with mock.patch.object(utils, 'exit') as mocked_utils_exit:
            mocked_utils_exit.return_value = '%s' % err_msg

            func(self.gc, func_args)

            mocked_utils_exit.assert_called_once_with(err_msg)

    def test_do_image_list(self):
        input = {
            'limit': None,
            'page_size': 18,
            'visibility': True,
            'member_status': 'Fake',
            'owner': 'test',
            'checksum': 'fake_checksum',
            'tag': 'fake tag',
            'properties': [],
            'sort_key': ['name', 'id'],
            'sort_dir': ['desc', 'asc'],
            'sort': None
        }
        args = self._make_args(input)
        with mock.patch.object(self.gc.images, 'list') as mocked_list:
            mocked_list.return_value = {}

            test_shell.do_image_list(self.gc, args)

            exp_img_filters = {
                'owner': 'test',
                'member_status': 'Fake',
                'visibility': True,
                'checksum': 'fake_checksum',
                'tag': 'fake tag'
            }
            mocked_list.assert_called_once_with(page_size=18,
                                                sort_key=['name', 'id'],
                                                sort_dir=['desc', 'asc'],
                                                filters=exp_img_filters)
            utils.print_list.assert_called_once_with({}, ['ID', 'Name'])

    def test_do_image_list_with_single_sort_key(self):
        input = {
            'limit': None,
            'page_size': 18,
            'visibility': True,
            'member_status': 'Fake',
            'owner': 'test',
            'checksum': 'fake_checksum',
            'tag': 'fake tag',
            'properties': [],
            'sort_key': ['name'],
            'sort_dir': ['desc'],
            'sort': None
        }
        args = self._make_args(input)
        with mock.patch.object(self.gc.images, 'list') as mocked_list:
            mocked_list.return_value = {}

            test_shell.do_image_list(self.gc, args)

            exp_img_filters = {
                'owner': 'test',
                'member_status': 'Fake',
                'visibility': True,
                'checksum': 'fake_checksum',
                'tag': 'fake tag'
            }
            mocked_list.assert_called_once_with(page_size=18,
                                                sort_key=['name'],
                                                sort_dir=['desc'],
                                                filters=exp_img_filters)
            utils.print_list.assert_called_once_with({}, ['ID', 'Name'])

    def test_do_image_list_new_sorting_syntax(self):
        input = {
            'limit': None,
            'page_size': 18,
            'visibility': True,
            'member_status': 'Fake',
            'owner': 'test',
            'checksum': 'fake_checksum',
            'tag': 'fake tag',
            'properties': [],
            'sort': 'name:desc,size:asc',
            'sort_key': [],
            'sort_dir': []
        }
        args = self._make_args(input)
        with mock.patch.object(self.gc.images, 'list') as mocked_list:
            mocked_list.return_value = {}

            test_shell.do_image_list(self.gc, args)

            exp_img_filters = {
                'owner': 'test',
                'member_status': 'Fake',
                'visibility': True,
                'checksum': 'fake_checksum',
                'tag': 'fake tag'
            }
            mocked_list.assert_called_once_with(
                page_size=18,
                sort='name:desc,size:asc',
                filters=exp_img_filters)
            utils.print_list.assert_called_once_with({}, ['ID', 'Name'])

    def test_do_image_list_with_property_filter(self):
        input = {
            'limit': None,
            'page_size': 1,
            'visibility': True,
            'member_status': 'Fake',
            'owner': 'test',
            'checksum': 'fake_checksum',
            'tag': 'fake tag',
            'properties': ['os_distro=NixOS', 'architecture=x86_64'],
            'sort_key': ['name'],
            'sort_dir': ['desc'],
            'sort': None
        }
        args = self._make_args(input)
        with mock.patch.object(self.gc.images, 'list') as mocked_list:
            mocked_list.return_value = {}

            test_shell.do_image_list(self.gc, args)

            exp_img_filters = {
                'owner': 'test',
                'member_status': 'Fake',
                'visibility': True,
                'checksum': 'fake_checksum',
                'tag': 'fake tag',
                'os_distro': 'NixOS',
                'architecture': 'x86_64'
            }

            mocked_list.assert_called_once_with(page_size=1,
                                                sort_key=['name'],
                                                sort_dir=['desc'],
                                                filters=exp_img_filters)
            utils.print_list.assert_called_once_with({}, ['ID', 'Name'])

    def test_do_image_show(self):
        args = self._make_args({'id': 'pass', 'page_size': 18,
                                'max_column_width': 120})
        with mock.patch.object(self.gc.images, 'get') as mocked_list:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            mocked_list.return_value = expect_image

            test_shell.do_image_show(self.gc, args)

            mocked_list.assert_called_once_with('pass')
            utils.print_dict.assert_called_once_with({'id': 'pass'},
                                                     max_column_width=120)

    @mock.patch('sys.stdin', autospec=True)
    def test_do_image_create_no_user_props(self, mock_stdin):
        args = self._make_args({'name': 'IMG-01', 'disk_format': 'vhd',
                                'container_format': 'bare',
                                'file': None})
        with mock.patch.object(self.gc.images, 'create') as mocked_create:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            expect_image['name'] = 'IMG-01'
            expect_image['disk_format'] = 'vhd'
            expect_image['container_format'] = 'bare'
            mocked_create.return_value = expect_image

            # Ensure that the test stdin is not considered
            # to be supplying image data
            mock_stdin.isatty = lambda: True
            test_shell.do_image_create(self.gc, args)

            mocked_create.assert_called_once_with(name='IMG-01',
                                                  disk_format='vhd',
                                                  container_format='bare')
            utils.print_dict.assert_called_once_with({
                'id': 'pass', 'name': 'IMG-01', 'disk_format': 'vhd',
                'container_format': 'bare'})

    def test_do_image_create_with_file(self):
        try:
            file_name = None
            with open(tempfile.mktemp(), 'w+') as f:
                f.write('Some data here')
                f.flush()
                f.seek(0)
                file_name = f.name
            temp_args = {'name': 'IMG-01',
                         'disk_format': 'vhd',
                         'container_format': 'bare',
                         'file': file_name,
                         'progress': False}
            args = self._make_args(temp_args)
            with mock.patch.object(self.gc.images, 'create') as mocked_create:
                with mock.patch.object(self.gc.images, 'get') as mocked_get:

                    ignore_fields = ['self', 'access', 'schema']
                    expect_image = dict([(field, field) for field in
                                         ignore_fields])
                    expect_image['id'] = 'pass'
                    expect_image['name'] = 'IMG-01'
                    expect_image['disk_format'] = 'vhd'
                    expect_image['container_format'] = 'bare'
                    mocked_create.return_value = expect_image
                    mocked_get.return_value = expect_image

                    test_shell.do_image_create(self.gc, args)

                    temp_args.pop('file', None)
                    mocked_create.assert_called_once_with(**temp_args)
                    mocked_get.assert_called_once_with('pass')
                    utils.print_dict.assert_called_once_with({
                        'id': 'pass', 'name': 'IMG-01', 'disk_format': 'vhd',
                        'container_format': 'bare'})
        finally:
            try:
                os.remove(f.name)
            except Exception:
                pass

    @mock.patch('sys.stdin', autospec=True)
    def test_do_image_create_with_user_props(self, mock_stdin):
        args = self._make_args({'name': 'IMG-01',
                                'property': ['myprop=myval'],
                                'file': None})
        with mock.patch.object(self.gc.images, 'create') as mocked_create:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            expect_image['name'] = 'IMG-01'
            expect_image['myprop'] = 'myval'
            mocked_create.return_value = expect_image

            # Ensure that the test stdin is not considered
            # to be supplying image data
            mock_stdin.isatty = lambda: True
            test_shell.do_image_create(self.gc, args)

            mocked_create.assert_called_once_with(name='IMG-01',
                                                  myprop='myval')
            utils.print_dict.assert_called_once_with({
                'id': 'pass', 'name': 'IMG-01', 'myprop': 'myval'})

    def test_do_image_update_no_user_props(self):
        args = self._make_args({'id': 'pass', 'name': 'IMG-01',
                                'disk_format': 'vhd',
                                'container_format': 'bare'})
        with mock.patch.object(self.gc.images, 'update') as mocked_update:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            expect_image['name'] = 'IMG-01'
            expect_image['disk_format'] = 'vhd'
            expect_image['container_format'] = 'bare'
            mocked_update.return_value = expect_image

            test_shell.do_image_update(self.gc, args)

            mocked_update.assert_called_once_with('pass',
                                                  None,
                                                  name='IMG-01',
                                                  disk_format='vhd',
                                                  container_format='bare')
            utils.print_dict.assert_called_once_with({
                'id': 'pass', 'name': 'IMG-01', 'disk_format': 'vhd',
                'container_format': 'bare'})

    def test_do_image_update_with_user_props(self):
        args = self._make_args({'id': 'pass', 'name': 'IMG-01',
                                'property': ['myprop=myval']})
        with mock.patch.object(self.gc.images, 'update') as mocked_update:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            expect_image['name'] = 'IMG-01'
            expect_image['myprop'] = 'myval'
            mocked_update.return_value = expect_image

            test_shell.do_image_update(self.gc, args)

            mocked_update.assert_called_once_with('pass',
                                                  None,
                                                  name='IMG-01',
                                                  myprop='myval')
            utils.print_dict.assert_called_once_with({
                'id': 'pass', 'name': 'IMG-01', 'myprop': 'myval'})

    def test_do_image_update_with_remove_props(self):
        args = self._make_args({'id': 'pass', 'name': 'IMG-01',
                                'disk_format': 'vhd',
                                'remove-property': ['container_format']})
        with mock.patch.object(self.gc.images, 'update') as mocked_update:
            ignore_fields = ['self', 'access', 'file', 'schema']
            expect_image = dict([(field, field) for field in ignore_fields])
            expect_image['id'] = 'pass'
            expect_image['name'] = 'IMG-01'
            expect_image['disk_format'] = 'vhd'

            mocked_update.return_value = expect_image

            test_shell.do_image_update(self.gc, args)

            mocked_update.assert_called_once_with('pass',
                                                  ['container_format'],
                                                  name='IMG-01',
                                                  disk_format='vhd')
            utils.print_dict.assert_called_once_with({
                'id': 'pass', 'name': 'IMG-01', 'disk_format': 'vhd'})

    def test_do_explain(self):
        input = {
            'page_size': 18,
            'id': 'pass',
            'schemas': 'test',
            'model': 'test',
        }
        args = self._make_args(input)
        with mock.patch.object(utils, 'print_list'):
            test_shell.do_explain(self.gc, args)

            self.gc.schemas.get.assert_called_once_with('test')

    def test_do_location_add(self):
        gc = self.gc
        loc = {'url': 'http://foo.com/', 'metadata': {'foo': 'bar'}}
        args = self._make_args({'id': 'pass',
                                'url': loc['url'],
                                'metadata': json.dumps(loc['metadata'])})
        with mock.patch.object(gc.images, 'add_location') as mocked_addloc:
            expect_image = {'id': 'pass', 'locations': [loc]}
            mocked_addloc.return_value = expect_image

            test_shell.do_location_add(self.gc, args)
            mocked_addloc.assert_called_once_with('pass',
                                                  loc['url'],
                                                  loc['metadata'])
            utils.print_dict.assert_called_once_with(expect_image)

    def test_do_location_delete(self):
        gc = self.gc
        loc_set = set(['http://foo/bar', 'http://spam/ham'])
        args = self._make_args({'id': 'pass', 'url': loc_set})

        with mock.patch.object(gc.images, 'delete_locations') as mocked_rmloc:
            test_shell.do_location_delete(self.gc, args)
            mocked_rmloc.assert_called_once_with('pass', loc_set)

    def test_do_location_update(self):
        gc = self.gc
        loc = {'url': 'http://foo.com/', 'metadata': {'foo': 'bar'}}
        args = self._make_args({'id': 'pass',
                                'url': loc['url'],
                                'metadata': json.dumps(loc['metadata'])})
        with mock.patch.object(gc.images, 'update_location') as mocked_modloc:
            expect_image = {'id': 'pass', 'locations': [loc]}
            mocked_modloc.return_value = expect_image

            test_shell.do_location_update(self.gc, args)
            mocked_modloc.assert_called_once_with('pass',
                                                  loc['url'],
                                                  loc['metadata'])
            utils.print_dict.assert_called_once_with(expect_image)

    def test_image_upload(self):
        args = self._make_args(
            {'id': 'IMG-01', 'file': 'test', 'size': 1024, 'progress': False})

        with mock.patch.object(self.gc.images, 'upload') as mocked_upload:
            utils.get_data_file = mock.Mock(return_value='testfile')
            mocked_upload.return_value = None
            test_shell.do_image_upload(self.gc, args)
            mocked_upload.assert_called_once_with('IMG-01', 'testfile', 1024)

    def test_image_download(self):
        args = self._make_args(
            {'id': 'IMG-01', 'file': 'test', 'progress': True})

        with mock.patch.object(self.gc.images, 'data') as mocked_data:
            def _data():
                for c in 'abcedf':
                    yield c
            mocked_data.return_value = utils.IterableWithLength(_data(), 5)

            test_shell.do_image_download(self.gc, args)
            mocked_data.assert_called_once_with('IMG-01')

    def test_do_image_delete(self):
        args = self._make_args({'id': 'pass', 'file': 'test'})
        with mock.patch.object(self.gc.images, 'delete') as mocked_delete:
            mocked_delete.return_value = 0

            test_shell.do_image_delete(self.gc, args)

            mocked_delete.assert_called_once_with('pass')

    def test_do_image_delete_deleted(self):
        image_id = 'deleted-img'
        args = self._make_args({'id': image_id})
        with mock.patch.object(self.gc.images, 'get') as mocked_get:
            mocked_get.return_value = self._make_args({'id': image_id,
                                                       'status': 'deleted'})

            msg = "No image with an ID of '%s' exists." % image_id
            self.assert_exits_with_msg(func=test_shell.do_image_delete,
                                       func_args=args,
                                       err_msg=msg)

    def test_do_member_list(self):
        args = self._make_args({'image_id': 'IMG-01'})
        with mock.patch.object(self.gc.image_members, 'list') as mocked_list:
            mocked_list.return_value = {}

            test_shell.do_member_list(self.gc, args)

            mocked_list.assert_called_once_with('IMG-01')
            columns = ['Image ID', 'Member ID', 'Status']
            utils.print_list.assert_called_once_with({}, columns)

    def test_do_member_create(self):
        args = self._make_args({'image_id': 'IMG-01', 'member_id': 'MEM-01'})
        with mock.patch.object(self.gc.image_members, 'create') as mock_create:
            mock_create.return_value = {}

            test_shell.do_member_create(self.gc, args)

            mock_create.assert_called_once_with('IMG-01', 'MEM-01')
            columns = ['Image ID', 'Member ID', 'Status']
            utils.print_list.assert_called_once_with([{}], columns)

    def test_do_member_create_with_few_arguments(self):
        args = self._make_args({'image_id': None, 'member_id': 'MEM-01'})
        msg = 'Unable to create member. Specify image_id and member_id'

        self.assert_exits_with_msg(func=test_shell.do_member_create,
                                   func_args=args,
                                   err_msg=msg)

    def test_do_member_update(self):
        input = {
            'image_id': 'IMG-01',
            'member_id': 'MEM-01',
            'member_status': 'status',
        }
        args = self._make_args(input)
        with mock.patch.object(self.gc.image_members, 'update') as mock_update:
            mock_update.return_value = {}

            test_shell.do_member_update(self.gc, args)

            mock_update.assert_called_once_with('IMG-01', 'MEM-01', 'status')
            columns = ['Image ID', 'Member ID', 'Status']
            utils.print_list.assert_called_once_with([{}], columns)

    def test_do_member_update_with_few_arguments(self):
        input = {
            'image_id': 'IMG-01',
            'member_id': 'MEM-01',
            'member_status': None,
        }
        args = self._make_args(input)
        msg = 'Unable to update member. Specify image_id, member_id' \
              ' and member_status'

        self.assert_exits_with_msg(func=test_shell.do_member_update,
                                   func_args=args,
                                   err_msg=msg)

    def test_do_member_delete(self):
        args = self._make_args({'image_id': 'IMG-01', 'member_id': 'MEM-01'})
        with mock.patch.object(self.gc.image_members, 'delete') as mock_delete:
            test_shell.do_member_delete(self.gc, args)

            mock_delete.assert_called_once_with('IMG-01', 'MEM-01')

    def test_do_member_delete_with_few_arguments(self):
        args = self._make_args({'image_id': None, 'member_id': 'MEM-01'})
        msg = 'Unable to delete member. Specify image_id and member_id'

        self.assert_exits_with_msg(func=test_shell.do_member_delete,
                                   func_args=args,
                                   err_msg=msg)

    def test_image_tag_update(self):
        args = self._make_args({'image_id': 'IMG-01', 'tag_value': 'tag01'})
        with mock.patch.object(self.gc.image_tags, 'update') as mocked_update:
            self.gc.images.get = mock.Mock(return_value={})
            mocked_update.return_value = None

            test_shell.do_image_tag_update(self.gc, args)

            mocked_update.assert_called_once_with('IMG-01', 'tag01')

    def test_image_tag_update_with_few_arguments(self):
        args = self._make_args({'image_id': None, 'tag_value': 'tag01'})
        msg = 'Unable to update tag. Specify image_id and tag_value'

        self.assert_exits_with_msg(func=test_shell.do_image_tag_update,
                                   func_args=args,
                                   err_msg=msg)

    def test_image_tag_delete(self):
        args = self._make_args({'image_id': 'IMG-01', 'tag_value': 'tag01'})
        with mock.patch.object(self.gc.image_tags, 'delete') as mocked_delete:
            mocked_delete.return_value = None

            test_shell.do_image_tag_delete(self.gc, args)

            mocked_delete.assert_called_once_with('IMG-01', 'tag01')

    def test_image_tag_delete_with_few_arguments(self):
        args = self._make_args({'image_id': 'IMG-01', 'tag_value': None})
        msg = 'Unable to delete tag. Specify image_id and tag_value'

        self.assert_exits_with_msg(func=test_shell.do_image_tag_delete,
                                   func_args=args,
                                   err_msg=msg)

    def test_do_md_namespace_create(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'protected': True})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'create') as mocked_create:
            expect_namespace = {}
            expect_namespace['namespace'] = 'MyNamespace'
            expect_namespace['protected'] = True

            mocked_create.return_value = expect_namespace

            test_shell.do_md_namespace_create(self.gc, args)

            mocked_create.assert_called_once_with(namespace='MyNamespace',
                                                  protected=True)
            utils.print_dict.assert_called_once_with(expect_namespace)

    def test_do_md_namespace_import(self):
        args = self._make_args({'file': 'test'})

        expect_namespace = {}
        expect_namespace['namespace'] = 'MyNamespace'
        expect_namespace['protected'] = True

        with mock.patch.object(self.gc.metadefs_namespace,
                               'create') as mocked_create:
            mock_read = mock.Mock(return_value=json.dumps(expect_namespace))
            mock_file = mock.Mock(read=mock_read)
            utils.get_data_file = mock.Mock(return_value=mock_file)
            mocked_create.return_value = expect_namespace

            test_shell.do_md_namespace_import(self.gc, args)

            mocked_create.assert_called_once_with(**expect_namespace)
            utils.print_dict.assert_called_once_with(expect_namespace)

    def test_do_md_namespace_import_invalid_json(self):
        args = self._make_args({'file': 'test'})
        mock_read = mock.Mock(return_value='Invalid')
        mock_file = mock.Mock(read=mock_read)
        utils.get_data_file = mock.Mock(return_value=mock_file)

        self.assertRaises(SystemExit, test_shell.do_md_namespace_import,
                          self.gc, args)

    def test_do_md_namespace_import_no_input(self):
        args = self._make_args({'file': None})
        utils.get_data_file = mock.Mock(return_value=None)

        self.assertRaises(SystemExit, test_shell.do_md_namespace_import,
                          self.gc, args)

    def test_do_md_namespace_update(self):
        args = self._make_args({'id': 'MyNamespace',
                                'protected': True})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'update') as mocked_update:
            expect_namespace = {}
            expect_namespace['namespace'] = 'MyNamespace'
            expect_namespace['protected'] = True

            mocked_update.return_value = expect_namespace

            test_shell.do_md_namespace_update(self.gc, args)

            mocked_update.assert_called_once_with('MyNamespace',
                                                  id='MyNamespace',
                                                  protected=True)
            utils.print_dict.assert_called_once_with(expect_namespace)

    def test_do_md_namespace_show(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'max_column_width': 80,
                                'resource_type': None})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'get') as mocked_get:
            expect_namespace = {}
            expect_namespace['namespace'] = 'MyNamespace'

            mocked_get.return_value = expect_namespace

            test_shell.do_md_namespace_show(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace')
            utils.print_dict.assert_called_once_with(expect_namespace, 80)

    def test_do_md_namespace_show_resource_type(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'max_column_width': 80,
                                'resource_type': 'RESOURCE'})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'get') as mocked_get:
            expect_namespace = {}
            expect_namespace['namespace'] = 'MyNamespace'

            mocked_get.return_value = expect_namespace

            test_shell.do_md_namespace_show(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace',
                                               resource_type='RESOURCE')
            utils.print_dict.assert_called_once_with(expect_namespace, 80)

    def test_do_md_namespace_list(self):
        args = self._make_args({'resource_type': None,
                                'visibility': None,
                                'page_size': None})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'list') as mocked_list:
            expect_namespaces = [{'namespace': 'MyNamespace'}]

            mocked_list.return_value = expect_namespaces

            test_shell.do_md_namespace_list(self.gc, args)

            mocked_list.assert_called_once_with(filters={})
            utils.print_list.assert_called_once_with(expect_namespaces,
                                                     ['namespace'])

    def test_do_md_namespace_list_page_size(self):
        args = self._make_args({'resource_type': None,
                                'visibility': None,
                                'page_size': 2})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'list') as mocked_list:
            expect_namespaces = [{'namespace': 'MyNamespace'}]

            mocked_list.return_value = expect_namespaces

            test_shell.do_md_namespace_list(self.gc, args)

            mocked_list.assert_called_once_with(filters={}, page_size=2)
            utils.print_list.assert_called_once_with(expect_namespaces,
                                                     ['namespace'])

    def test_do_md_namespace_list_one_filter(self):
        args = self._make_args({'resource_types': ['OS::Compute::Aggregate'],
                                'visibility': None,
                                'page_size': None})
        with mock.patch.object(self.gc.metadefs_namespace, 'list') as \
                mocked_list:
            expect_namespaces = [{'namespace': 'MyNamespace'}]

            mocked_list.return_value = expect_namespaces

            test_shell.do_md_namespace_list(self.gc, args)

            mocked_list.assert_called_once_with(filters={
                'resource_types': ['OS::Compute::Aggregate']})
            utils.print_list.assert_called_once_with(expect_namespaces,
                                                     ['namespace'])

    def test_do_md_namespace_list_all_filters(self):
        args = self._make_args({'resource_types': ['OS::Compute::Aggregate'],
                                'visibility': 'public',
                                'page_size': None})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'list') as mocked_list:
            expect_namespaces = [{'namespace': 'MyNamespace'}]

            mocked_list.return_value = expect_namespaces

            test_shell.do_md_namespace_list(self.gc, args)

            mocked_list.assert_called_once_with(filters={
                'resource_types': ['OS::Compute::Aggregate'],
                'visibility': 'public'})
            utils.print_list.assert_called_once_with(expect_namespaces,
                                                     ['namespace'])

    def test_do_md_namespace_list_unknown_filter(self):
        args = self._make_args({'resource_type': None,
                                'visibility': None,
                                'some_arg': 'some_value',
                                'page_size': None})
        with mock.patch.object(self.gc.metadefs_namespace,
                               'list') as mocked_list:
            expect_namespaces = [{'namespace': 'MyNamespace'}]

            mocked_list.return_value = expect_namespaces

            test_shell.do_md_namespace_list(self.gc, args)

            mocked_list.assert_called_once_with(filters={})
            utils.print_list.assert_called_once_with(expect_namespaces,
                                                     ['namespace'])

    def test_do_md_namespace_delete(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'content': False})
        with mock.patch.object(self.gc.metadefs_namespace, 'delete') as \
                mocked_delete:
            test_shell.do_md_namespace_delete(self.gc, args)

            mocked_delete.assert_called_once_with('MyNamespace')

    def test_do_md_resource_type_associate(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'name': 'MyResourceType',
                                'prefix': 'PREFIX:'})
        with mock.patch.object(self.gc.metadefs_resource_type,
                               'associate') as mocked_associate:
            expect_rt = {}
            expect_rt['namespace'] = 'MyNamespace'
            expect_rt['name'] = 'MyResourceType'
            expect_rt['prefix'] = 'PREFIX:'

            mocked_associate.return_value = expect_rt

            test_shell.do_md_resource_type_associate(self.gc, args)

            mocked_associate.assert_called_once_with('MyNamespace',
                                                     **expect_rt)
            utils.print_dict.assert_called_once_with(expect_rt)

    def test_do_md_resource_type_deassociate(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'resource_type': 'MyResourceType'})
        with mock.patch.object(self.gc.metadefs_resource_type,
                               'deassociate') as mocked_deassociate:
            test_shell.do_md_resource_type_deassociate(self.gc, args)

            mocked_deassociate.assert_called_once_with('MyNamespace',
                                                       'MyResourceType')

    def test_do_md_resource_type_list(self):
        args = self._make_args({})
        with mock.patch.object(self.gc.metadefs_resource_type,
                               'list') as mocked_list:
            expect_objects = ['MyResourceType1', 'MyResourceType2']

            mocked_list.return_value = expect_objects

            test_shell.do_md_resource_type_list(self.gc, args)

            mocked_list.assert_called_once()

    def test_do_md_namespace_resource_type_list(self):
        args = self._make_args({'namespace': 'MyNamespace'})
        with mock.patch.object(self.gc.metadefs_resource_type,
                               'get') as mocked_get:
            expect_objects = [{'namespace': 'MyNamespace',
                               'object': 'MyObject'}]

            mocked_get.return_value = expect_objects

            test_shell.do_md_namespace_resource_type_list(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace')
            utils.print_list.assert_called_once_with(expect_objects,
                                                     ['name', 'prefix',
                                                      'properties_target'])

    def test_do_md_property_create(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'name': "MyProperty",
                                'title': "Title",
                                'schema': '{}'})
        with mock.patch.object(self.gc.metadefs_property,
                               'create') as mocked_create:
            expect_property = {}
            expect_property['namespace'] = 'MyNamespace'
            expect_property['name'] = 'MyProperty'
            expect_property['title'] = 'Title'

            mocked_create.return_value = expect_property

            test_shell.do_md_property_create(self.gc, args)

            mocked_create.assert_called_once_with('MyNamespace',
                                                  name='MyProperty',
                                                  title='Title')
            utils.print_dict.assert_called_once_with(expect_property)

    def test_do_md_property_create_invalid_schema(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'name': "MyProperty",
                                'title': "Title",
                                'schema': 'Invalid'})
        self.assertRaises(SystemExit, test_shell.do_md_property_create,
                          self.gc, args)

    def test_do_md_property_update(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'property': 'MyProperty',
                                'name': 'NewName',
                                'title': "Title",
                                'schema': '{}'})
        with mock.patch.object(self.gc.metadefs_property,
                               'update') as mocked_update:
            expect_property = {}
            expect_property['namespace'] = 'MyNamespace'
            expect_property['name'] = 'MyProperty'
            expect_property['title'] = 'Title'

            mocked_update.return_value = expect_property

            test_shell.do_md_property_update(self.gc, args)

            mocked_update.assert_called_once_with('MyNamespace', 'MyProperty',
                                                  name='NewName',
                                                  title='Title')
            utils.print_dict.assert_called_once_with(expect_property)

    def test_do_md_property_update_invalid_schema(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'property': 'MyProperty',
                                'name': "MyObject",
                                'title': "Title",
                                'schema': 'Invalid'})
        self.assertRaises(SystemExit, test_shell.do_md_property_update,
                          self.gc, args)

    def test_do_md_property_show(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'property': 'MyProperty',
                                'max_column_width': 80})
        with mock.patch.object(self.gc.metadefs_property, 'get') as mocked_get:
            expect_property = {}
            expect_property['namespace'] = 'MyNamespace'
            expect_property['property'] = 'MyProperty'
            expect_property['title'] = 'Title'

            mocked_get.return_value = expect_property

            test_shell.do_md_property_show(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace', 'MyProperty')
            utils.print_dict.assert_called_once_with(expect_property, 80)

    def test_do_md_property_delete(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'property': 'MyProperty'})
        with mock.patch.object(self.gc.metadefs_property,
                               'delete') as mocked_delete:
            test_shell.do_md_property_delete(self.gc, args)

            mocked_delete.assert_called_once_with('MyNamespace', 'MyProperty')

    def test_do_md_namespace_property_delete(self):
        args = self._make_args({'namespace': 'MyNamespace'})
        with mock.patch.object(self.gc.metadefs_property,
                               'delete_all') as mocked_delete_all:
            test_shell.do_md_namespace_properties_delete(self.gc, args)

            mocked_delete_all.assert_called_once_with('MyNamespace')

    def test_do_md_property_list(self):
        args = self._make_args({'namespace': 'MyNamespace'})
        with mock.patch.object(self.gc.metadefs_property,
                               'list') as mocked_list:
            expect_objects = [{'namespace': 'MyNamespace',
                               'property': 'MyProperty',
                               'title': 'MyTitle'}]

            mocked_list.return_value = expect_objects

            test_shell.do_md_property_list(self.gc, args)

            mocked_list.assert_called_once_with('MyNamespace')
            utils.print_list.assert_called_once_with(expect_objects,
                                                     ['name', 'title', 'type'])

    def test_do_md_object_create(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'name': "MyObject",
                                'schema': '{}'})
        with mock.patch.object(self.gc.metadefs_object,
                               'create') as mocked_create:
            expect_object = {}
            expect_object['namespace'] = 'MyNamespace'
            expect_object['name'] = 'MyObject'

            mocked_create.return_value = expect_object

            test_shell.do_md_object_create(self.gc, args)

            mocked_create.assert_called_once_with('MyNamespace',
                                                  name='MyObject')
            utils.print_dict.assert_called_once_with(expect_object)

    def test_do_md_object_create_invalid_schema(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'name': "MyObject",
                                'schema': 'Invalid'})
        self.assertRaises(SystemExit, test_shell.do_md_object_create,
                          self.gc, args)

    def test_do_md_object_update(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject',
                                'name': 'NewName',
                                'schema': '{}'})
        with mock.patch.object(self.gc.metadefs_object,
                               'update') as mocked_update:
            expect_object = {}
            expect_object['namespace'] = 'MyNamespace'
            expect_object['name'] = 'MyObject'

            mocked_update.return_value = expect_object

            test_shell.do_md_object_update(self.gc, args)

            mocked_update.assert_called_once_with('MyNamespace', 'MyObject',
                                                  name='NewName')
            utils.print_dict.assert_called_once_with(expect_object)

    def test_do_md_object_update_invalid_schema(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject',
                                'name': "MyObject",
                                'schema': 'Invalid'})
        self.assertRaises(SystemExit, test_shell.do_md_object_update,
                          self.gc, args)

    def test_do_md_object_show(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject',
                                'max_column_width': 80})
        with mock.patch.object(self.gc.metadefs_object, 'get') as mocked_get:
            expect_object = {}
            expect_object['namespace'] = 'MyNamespace'
            expect_object['object'] = 'MyObject'

            mocked_get.return_value = expect_object

            test_shell.do_md_object_show(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace', 'MyObject')
            utils.print_dict.assert_called_once_with(expect_object, 80)

    def test_do_md_object_property_show(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject',
                                'property': 'MyProperty',
                                'max_column_width': 80})
        with mock.patch.object(self.gc.metadefs_object, 'get') as mocked_get:
            expect_object = {'name': 'MyObject',
                             'properties': {
                                 'MyProperty': {'type': 'string'}
                             }}

            mocked_get.return_value = expect_object

            test_shell.do_md_object_property_show(self.gc, args)

            mocked_get.assert_called_once_with('MyNamespace', 'MyObject')
            utils.print_dict.assert_called_once_with({'type': 'string',
                                                      'name': 'MyProperty'},
                                                     80)

    def test_do_md_object_property_show_non_existing(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject',
                                'property': 'MyProperty',
                                'max_column_width': 80})
        with mock.patch.object(self.gc.metadefs_object, 'get') as mocked_get:
            expect_object = {'name': 'MyObject', 'properties': {}}
            mocked_get.return_value = expect_object

            self.assertRaises(SystemExit,
                              test_shell.do_md_object_property_show,
                              self.gc, args)
            mocked_get.assert_called_once_with('MyNamespace', 'MyObject')

    def test_do_md_object_delete(self):
        args = self._make_args({'namespace': 'MyNamespace',
                                'object': 'MyObject'})
        with mock.patch.object(self.gc.metadefs_object,
                               'delete') as mocked_delete:
            test_shell.do_md_object_delete(self.gc, args)

            mocked_delete.assert_called_once_with('MyNamespace', 'MyObject')

    def test_do_md_namespace_objects_delete(self):
        args = self._make_args({'namespace': 'MyNamespace'})
        with mock.patch.object(self.gc.metadefs_object,
                               'delete_all') as mocked_delete_all:
            test_shell.do_md_namespace_objects_delete(self.gc, args)

            mocked_delete_all.assert_called_once_with('MyNamespace')

    def test_do_md_object_list(self):
        args = self._make_args({'namespace': 'MyNamespace'})
        with mock.patch.object(self.gc.metadefs_object, 'list') as mocked_list:
            expect_objects = [{'namespace': 'MyNamespace',
                               'object': 'MyObject'}]

            mocked_list.return_value = expect_objects

            test_shell.do_md_object_list(self.gc, args)

            mocked_list.assert_called_once_with('MyNamespace')
            utils.print_list.assert_called_once_with(
                expect_objects,
                ['name', 'description'],
                field_settings={
                    'description': {'align': 'l', 'max_width': 50}})
