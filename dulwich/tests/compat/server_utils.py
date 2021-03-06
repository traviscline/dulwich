# server_utils.py -- Git server compatibility utilities
# Copyright (C) 2010 Google, Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License or (at your option) any later version of
# the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.

"""Utilities for testing git server compatibility."""


import select
import socket
import threading

from dulwich.tests.utils import (
    tear_down_repo,
    )
from utils import (
    import_repo,
    run_git,
    )


class ServerTests(object):
    """Base tests for testing servers.

    Does not inherit from TestCase so tests are not automatically run.
    """

    def setUp(self):
        self._old_repo = import_repo('server_old.export')
        self._new_repo = import_repo('server_new.export')
        self._server = None

    def tearDown(self):
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        tear_down_repo(self._old_repo)
        tear_down_repo(self._new_repo)

    def assertReposEqual(self, repo1, repo2):
        self.assertEqual(repo1.get_refs(), repo2.get_refs())
        self.assertEqual(set(repo1.object_store), set(repo2.object_store))

    def assertReposNotEqual(self, repo1, repo2):
        refs1 = repo1.get_refs()
        objs1 = set(repo1.object_store)
        refs2 = repo2.get_refs()
        objs2 = set(repo2.object_store)

        self.assertFalse(refs1 == refs2 and objs1 == objs2)

    def test_push_to_dulwich(self):
        self.assertReposNotEqual(self._old_repo, self._new_repo)
        port = self._start_server(self._old_repo)

        all_branches = ['master', 'branch']
        branch_args = ['%s:%s' % (b, b) for b in all_branches]
        url = '%s://localhost:%s/' % (self.protocol, port)
        returncode, _ = run_git(['push', url] + branch_args,
                                cwd=self._new_repo.path)
        self.assertEqual(0, returncode)
        self.assertReposEqual(self._old_repo, self._new_repo)

    def test_fetch_from_dulwich(self):
        self.assertReposNotEqual(self._old_repo, self._new_repo)
        port = self._start_server(self._new_repo)

        all_branches = ['master', 'branch']
        branch_args = ['%s:%s' % (b, b) for b in all_branches]
        url = '%s://localhost:%s/' % (self.protocol, port)
        returncode, _ = run_git(['fetch', url] + branch_args,
                                cwd=self._old_repo.path)
        # flush the pack cache so any new packs are picked up
        self._old_repo.object_store._pack_cache = None
        self.assertEqual(0, returncode)
        self.assertReposEqual(self._old_repo, self._new_repo)


class ShutdownServerMixIn:
    """Mixin that allows serve_forever to be shut down.

    The methods in this mixin are backported from SocketServer.py in the Python
    2.6.4 standard library. The mixin is unnecessary in 2.6 and later, when
    BaseServer supports the shutdown method directly.
    """

    def __init__(self):
        self.__is_shut_down = threading.Event()
        self.__serving = False

    def serve_forever(self, poll_interval=0.5):
        """Handle one request at a time until shutdown.

        Polls for shutdown every poll_interval seconds. Ignores
        self.timeout. If you need to do periodic tasks, do them in
        another thread.
        """
        self.__serving = True
        self.__is_shut_down.clear()
        while self.__serving:
            # XXX: Consider using another file descriptor or
            # connecting to the socket to wake this up instead of
            # polling. Polling reduces our responsiveness to a
            # shutdown request and wastes cpu at all other times.
            r, w, e = select.select([self], [], [], poll_interval)
            if r:
                self._handle_request_noblock()
        self.__is_shut_down.set()

    serve = serve_forever  # override alias from TCPGitServer

    def shutdown(self):
        """Stops the serve_forever loop.

        Blocks until the loop has finished. This must be called while
        serve_forever() is running in another thread, or it will deadlock.
        """
        self.__serving = False
        self.__is_shut_down.wait()

    def handle_request(self):
        """Handle one request, possibly blocking.

        Respects self.timeout.
        """
        # Support people who used socket.settimeout() to escape
        # handle_request before self.timeout was available.
        timeout = self.socket.gettimeout()
        if timeout is None:
            timeout = self.timeout
        elif self.timeout is not None:
            timeout = min(timeout, self.timeout)
        fd_sets = select.select([self], [], [], timeout)
        if not fd_sets[0]:
            self.handle_timeout()
            return
        self._handle_request_noblock()

    def _handle_request_noblock(self):
        """Handle one request, without blocking.

        I assume that select.select has returned that the socket is
        readable before this function was called, so there should be
        no risk of blocking in get_request().
        """
        try:
            request, client_address = self.get_request()
        except socket.error:
            return
        if self.verify_request(request, client_address):
            try:
                self.process_request(request, client_address)
            except:
                self.handle_error(request, client_address)
                self.close_request(request)
