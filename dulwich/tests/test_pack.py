# test_pack.py -- Tests for the handling of git packs.
# Copyright (C) 2007 James Westby <jw+debian@jameswestby.net>
# Copyright (C) 2008 Jelmer Vernooij <jelmer@samba.org>
# 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; version 2
# of the License, or (at your option) any later version of the license.
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


"""Tests for Dulwich packs."""


from cStringIO import StringIO
import os
import unittest
import zlib

from dulwich.objects import (
    Tree,
    )
from dulwich.pack import (
    Pack,
    PackData,
    apply_delta,
    create_delta,
    load_pack_index,
    hex_to_sha,
    read_zlib_chunks,
    sha_to_hex,
    write_pack_index_v1,
    write_pack_index_v2,
    write_pack,
    )

pack1_sha = 'bc63ddad95e7321ee734ea11a7a62d314e0d7481'

a_sha = '6f670c0fb53f9463760b7295fbb814e965fb20c8'
tree_sha = 'b2a2766a2879c209ab1176e7e778b81ae422eeaa'
commit_sha = 'f18faa16531ac570a3fdc8c7ca16682548dafd12'

class PackTests(unittest.TestCase):
    """Base class for testing packs"""
  
    datadir = os.path.join(os.path.dirname(__file__), 'data/packs')
  
    def get_pack_index(self, sha):
        """Returns a PackIndex from the datadir with the given sha"""
        return load_pack_index(os.path.join(self.datadir, 'pack-%s.idx' % sha))
  
    def get_pack_data(self, sha):
        """Returns a PackData object from the datadir with the given sha"""
        return PackData(os.path.join(self.datadir, 'pack-%s.pack' % sha))
  
    def get_pack(self, sha):
        return Pack(os.path.join(self.datadir, 'pack-%s' % sha))


class PackIndexTests(PackTests):
    """Class that tests the index of packfiles"""
  
    def test_object_index(self):
        """Tests that the correct object offset is returned from the index."""
        p = self.get_pack_index(pack1_sha)
        self.assertRaises(KeyError, p.object_index, pack1_sha)
        self.assertEqual(p.object_index(a_sha), 178)
        self.assertEqual(p.object_index(tree_sha), 138)
        self.assertEqual(p.object_index(commit_sha), 12)
  
    def test_index_len(self):
        p = self.get_pack_index(pack1_sha)
        self.assertEquals(3, len(p))
  
    def test_get_stored_checksum(self):
        p = self.get_pack_index(pack1_sha)
        self.assertEquals("\xf2\x84\x8e*\xd1o2\x9a\xe1\xc9.;\x95\xe9\x18\x88\xda\xa5\xbd\x01", str(p.get_stored_checksum()))
        self.assertEquals( 'r\x19\x80\xe8f\xaf\x9a_\x93\xadgAD\xe1E\x9b\x8b\xa3\xe7\xb7' , str(p.get_pack_checksum()))
  
    def test_index_check(self):
        p = self.get_pack_index(pack1_sha)
        self.assertEquals(True, p.check())
  
    def test_iterentries(self):
        p = self.get_pack_index(pack1_sha)
        self.assertEquals([('og\x0c\x0f\xb5?\x94cv\x0br\x95\xfb\xb8\x14\xe9e\xfb \xc8', 178, None), ('\xb2\xa2vj(y\xc2\t\xab\x11v\xe7\xe7x\xb8\x1a\xe4"\xee\xaa', 138, None), ('\xf1\x8f\xaa\x16S\x1a\xc5p\xa3\xfd\xc8\xc7\xca\x16h%H\xda\xfd\x12', 12, None)], list(p.iterentries()))
  
    def test_iter(self):
        p = self.get_pack_index(pack1_sha)
        self.assertEquals(set([tree_sha, commit_sha, a_sha]), set(p))
  

class TestPackDeltas(unittest.TestCase):
  
    test_string1 = "The answer was flailing in the wind"
    test_string2 = "The answer was falling down the pipe"
    test_string3 = "zzzzz"
  
    test_string_empty = ""
    test_string_big = "Z" * 8192
  
    def _test_roundtrip(self, base, target):
        self.assertEquals([target],
            apply_delta(base, create_delta(base, target)))
  
    def test_nochange(self):
        self._test_roundtrip(self.test_string1, self.test_string1)
  
    def test_change(self):
        self._test_roundtrip(self.test_string1, self.test_string2)
  
    def test_rewrite(self):
        self._test_roundtrip(self.test_string1, self.test_string3)
  
    def test_overflow(self):
        self._test_roundtrip(self.test_string_empty, self.test_string_big)


class TestPackData(PackTests):
    """Tests getting the data from the packfile."""
  
    def test_create_pack(self):
        p = self.get_pack_data(pack1_sha)
  
    def test_pack_len(self):
        p = self.get_pack_data(pack1_sha)
        self.assertEquals(3, len(p))
  
    def test_index_check(self):
        p = self.get_pack_data(pack1_sha)
        self.assertEquals(True, p.check())
  
    def test_iterobjects(self):
        p = self.get_pack_data(pack1_sha)
        self.assertEquals([(12, 1, 'tree b2a2766a2879c209ab1176e7e778b81ae422eeaa\nauthor James Westby <jw+debian@jameswestby.net> 1174945067 +0100\ncommitter James Westby <jw+debian@jameswestby.net> 1174945067 +0100\n\nTest commit\n', 3775879613L), (138, 2, '100644 a\x00og\x0c\x0f\xb5?\x94cv\x0br\x95\xfb\xb8\x14\xe9e\xfb \xc8', 912998690L), (178, 3, 'test 1\n', 1373561701L)], [(len, type, "".join(chunks), offset) for (len, type, chunks, offset) in p.iterobjects()])
  
    def test_iterentries(self):
        p = self.get_pack_data(pack1_sha)
        self.assertEquals(set([('og\x0c\x0f\xb5?\x94cv\x0br\x95\xfb\xb8\x14\xe9e\xfb \xc8', 178, 1373561701L), ('\xb2\xa2vj(y\xc2\t\xab\x11v\xe7\xe7x\xb8\x1a\xe4"\xee\xaa', 138, 912998690L), ('\xf1\x8f\xaa\x16S\x1a\xc5p\xa3\xfd\xc8\xc7\xca\x16h%H\xda\xfd\x12', 12, 3775879613L)]), set(p.iterentries()))
  
    def test_create_index_v1(self):
        p = self.get_pack_data(pack1_sha)
        p.create_index_v1("v1test.idx")
        idx1 = load_pack_index("v1test.idx")
        idx2 = self.get_pack_index(pack1_sha)
        self.assertEquals(idx1, idx2)
  
    def test_create_index_v2(self):
        p = self.get_pack_data(pack1_sha)
        p.create_index_v2("v2test.idx")
        idx1 = load_pack_index("v2test.idx")
        idx2 = self.get_pack_index(pack1_sha)
        self.assertEquals(idx1, idx2)


class TestPack(PackTests):

    def test_len(self):
        p = self.get_pack(pack1_sha)
        self.assertEquals(3, len(p))

    def test_contains(self):
        p = self.get_pack(pack1_sha)
        self.assertTrue(tree_sha in p)

    def test_get(self):
        p = self.get_pack(pack1_sha)
        self.assertEquals(type(p[tree_sha]), Tree)

    def test_iter(self):
        p = self.get_pack(pack1_sha)
        self.assertEquals(set([tree_sha, commit_sha, a_sha]), set(p))

    def test_get_object_at(self):
        """Tests random access for non-delta objects"""
        p = self.get_pack(pack1_sha)
        obj = p[a_sha]
        self.assertEqual(obj.type_name, 'blob')
        self.assertEqual(obj.sha().hexdigest(), a_sha)
        obj = p[tree_sha]
        self.assertEqual(obj.type_name, 'tree')
        self.assertEqual(obj.sha().hexdigest(), tree_sha)
        obj = p[commit_sha]
        self.assertEqual(obj.type_name, 'commit')
        self.assertEqual(obj.sha().hexdigest(), commit_sha)

    def test_copy(self):
        origpack = self.get_pack(pack1_sha)
        self.assertEquals(True, origpack.index.check())
        write_pack("Elch", [(x, "") for x in origpack.iterobjects()], 
            len(origpack))
        newpack = Pack("Elch")
        self.assertEquals(origpack, newpack)
        self.assertEquals(True, newpack.index.check())
        self.assertEquals(origpack.name(), newpack.name())
        self.assertEquals(origpack.index.get_pack_checksum(), 
                          newpack.index.get_pack_checksum())
        
        self.assertTrue(
                (origpack.index.version != newpack.index.version) or
                (origpack.index.get_stored_checksum() == newpack.index.get_stored_checksum()))

    def test_commit_obj(self):
        p = self.get_pack(pack1_sha)
        commit = p[commit_sha]
        self.assertEquals("James Westby <jw+debian@jameswestby.net>",
            commit.author)
        self.assertEquals([], commit.parents)

    def test_name(self):
        p = self.get_pack(pack1_sha)
        self.assertEquals(pack1_sha, p.name())


class TestHexToSha(unittest.TestCase):

    def test_simple(self):
        self.assertEquals('\xab\xcd' * 10, hex_to_sha("abcd" * 10))

    def test_reverse(self):
        self.assertEquals("abcd" * 10, sha_to_hex('\xab\xcd' * 10))


class BaseTestPackIndexWriting(object):

    def test_empty(self):
        pack_checksum = 'r\x19\x80\xe8f\xaf\x9a_\x93\xadgAD\xe1E\x9b\x8b\xa3\xe7\xb7'
        self._write_fn("empty.idx", [], pack_checksum)
        idx = load_pack_index("empty.idx")
        self.assertTrue(idx.check())
        self.assertEquals(idx.get_pack_checksum(), pack_checksum)
        self.assertEquals(0, len(idx))

    def test_single(self):
        pack_checksum = 'r\x19\x80\xe8f\xaf\x9a_\x93\xadgAD\xe1E\x9b\x8b\xa3\xe7\xb7'
        my_entries = [('og\x0c\x0f\xb5?\x94cv\x0br\x95\xfb\xb8\x14\xe9e\xfb \xc8', 178, 42)]
        my_entries.sort()
        self._write_fn("single.idx", my_entries, pack_checksum)
        idx = load_pack_index("single.idx")
        self.assertEquals(idx.version, self._expected_version)
        self.assertTrue(idx.check())
        self.assertEquals(idx.get_pack_checksum(), pack_checksum)
        self.assertEquals(1, len(idx))
        actual_entries = list(idx.iterentries())
        self.assertEquals(len(my_entries), len(actual_entries))
        for a, b in zip(my_entries, actual_entries):
            self.assertEquals(a[0], b[0])
            self.assertEquals(a[1], b[1])
            if self._has_crc32_checksum:
                self.assertEquals(a[2], b[2])
            else:
                self.assertTrue(b[2] is None)


class TestPackIndexWritingv1(unittest.TestCase, BaseTestPackIndexWriting):

    def setUp(self):
        unittest.TestCase.setUp(self)
        self._has_crc32_checksum = False
        self._expected_version = 1
        self._write_fn = write_pack_index_v1


class TestPackIndexWritingv2(unittest.TestCase, BaseTestPackIndexWriting):

    def setUp(self):
        unittest.TestCase.setUp(self)
        self._has_crc32_checksum = True
        self._expected_version = 2
        self._write_fn = write_pack_index_v2


class ReadZlibTests(unittest.TestCase):

    decomp = (
      'tree 4ada885c9196b6b6fa08744b5862bf92896fc002\n'
      'parent None\n'
      'author Jelmer Vernooij <jelmer@samba.org> 1228980214 +0000\n'
      'committer Jelmer Vernooij <jelmer@samba.org> 1228980214 +0000\n'
      '\n'
      "Provide replacement for mmap()'s offset argument.")
    comp = zlib.compress(decomp)
    extra = 'nextobject'

    def setUp(self):
        self.read = StringIO(self.comp + self.extra).read

    def test_decompress_size(self):
        good_decomp_len = len(self.decomp)
        self.assertRaises(ValueError, read_zlib_chunks, self.read, -1)
        self.assertRaises(zlib.error, read_zlib_chunks, self.read,
                          good_decomp_len - 1)
        self.assertRaises(zlib.error, read_zlib_chunks, self.read,
                          good_decomp_len + 1)

    def test_decompress_truncated(self):
        read = StringIO(self.comp[:10]).read
        self.assertRaises(zlib.error, read_zlib_chunks, read, len(self.decomp))

        read = StringIO(self.comp).read
        self.assertRaises(zlib.error, read_zlib_chunks, read, len(self.decomp))

    def test_decompress_empty(self):
        comp = zlib.compress('')
        read = StringIO(comp + self.extra).read
        decomp, comp_len, unused_data = read_zlib_chunks(read, 0)
        self.assertEqual('', ''.join(decomp))
        self.assertEqual(len(comp), comp_len)
        self.assertNotEquals('', unused_data)
        self.assertEquals(self.extra, unused_data + read())

    def _do_decompress_test(self, buffer_size):
        decomp, comp_len, unused_data = read_zlib_chunks(
          self.read, len(self.decomp), buffer_size=buffer_size)
        self.assertEquals(self.decomp, ''.join(decomp))
        self.assertEquals(len(self.comp), comp_len)
        self.assertNotEquals('', unused_data)
        self.assertEquals(self.extra, unused_data + self.read())

    def test_simple_decompress(self):
        self._do_decompress_test(4096)

    # These buffer sizes are not intended to be realistic, but rather simulate
    # larger buffer sizes that may end at various places.
    def test_decompress_buffer_size_1(self):
        self._do_decompress_test(1)

    def test_decompress_buffer_size_2(self):
        self._do_decompress_test(2)

    def test_decompress_buffer_size_3(self):
        self._do_decompress_test(3)

    def test_decompress_buffer_size_4(self):
        self._do_decompress_test(4)
