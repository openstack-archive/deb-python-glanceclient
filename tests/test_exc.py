# Copyright 2012 OpenStack Foundation
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
import mock
import testtools

from glanceclient import exc


class TestHTTPExceptions(testtools.TestCase):
    def test_from_response(self):
        """exc.from_response should return instance of an HTTP exception."""
        mock_resp = mock.Mock()
        mock_resp.status_code = 400
        out = exc.from_response(mock_resp)
        self.assertIsInstance(out, exc.HTTPBadRequest)
