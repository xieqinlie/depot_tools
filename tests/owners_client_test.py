# Copyright (c) 2020 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import sys
import unittest

if sys.version_info.major == 2:
  import mock
else:
  from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gerrit_util
import owners_client

from testing_support import filesystem_mock


alice = 'alice@example.com'
bob = 'bob@example.com'
chris = 'chris@example.com'
dave = 'dave@example.com'
emily = 'emily@example.com'


def _get_owners():
  return [
    {
      "account": {
        "email": 'approver@example.com'
      }
    },
    {
      "account": {
        "email": 'reviewer@example.com'
      },
    },
    {
      "account": {
        "email": 'missing@example.com'
      },
    }
  ]



class DepotToolsClientTest(unittest.TestCase):
  def setUp(self):
    self.repo = filesystem_mock.MockFileSystem(files={
        '/OWNERS': '\n'.join([
            'per-file approved.cc=approver@example.com',
            'per-file reviewed.h=reviewer@example.com',
            'missing@example.com',
        ]),
        '/approved.cc': '',
        '/reviewed.h': '',
        '/bar/insufficient_reviewers.py': '',
        '/bar/everyone/OWNERS': '*',
        '/bar/everyone/foo.txt': '',
    })
    self.root = '/'
    self.fopen = self.repo.open_for_reading
    mock.patch(
        'owners_client.DepotToolsClient._GetOriginalOwnersFiles',
        return_value={}).start()
    self.addCleanup(mock.patch.stopall)
    self.client = owners_client.DepotToolsClient(
        '/', 'branch', self.fopen, self.repo)

  def testListOwners(self):
    self.assertEqual(
        ['*', 'missing@example.com'],
        self.client.ListOwners('bar/everyone/foo.txt'))


class GerritClientTest(unittest.TestCase):
  def setUp(self):
    self.client = owners_client.GerritClient('host', 'project', 'branch')

  @mock.patch('gerrit_util.GetOwnersForFile', return_value=_get_owners())
  def testListOwners(self, _get_owners_mock):
    self.assertEquals(
        ['approver@example.com', 'reviewer@example.com', 'missing@example.com'],
        self.client.ListOwners('bar/everyone/foo.txt'))


class TestClient(owners_client.OwnersClient):
  def __init__(self, owners_by_path):
    super(TestClient, self).__init__()
    self.owners_by_path = owners_by_path

  def ListOwners(self, path):
    return self.owners_by_path[path]


class OwnersClientTest(unittest.TestCase):
  def setUp(self):
    self.owners = {}
    self.client = TestClient(self.owners)

  def testGetFilesApprovalStatus(self):
    self.client.owners_by_path = {
      'approved': ['approver@example.com'],
      'pending': ['reviewer@example.com'],
      'insufficient': ['insufficient@example.com'],
    }
    status = self.client.GetFilesApprovalStatus(
        ['approved', 'pending', 'insufficient'],
        ['approver@example.com'], ['reviewer@example.com'])
    self.assertEqual(
        status,
        {
            'approved': owners_client.APPROVED,
            'pending': owners_client.PENDING,
            'insufficient': owners_client.INSUFFICIENT_REVIEWERS,
        })

  def test_owner_combinations(self):
    owners = [alice, bob, chris, dave, emily]
    self.assertEqual(
        list(owners_client._owner_combinations(owners, 2)),
        [(bob, alice),
         (chris, alice),
         (chris, bob),
         (dave, alice),
         (dave, bob),
         (dave, chris),
         (emily, alice),
         (emily, bob),
         (emily, chris),
         (emily, dave)])

  def testSuggestOwners(self):
    self.client.owners_by_path = {'a': [alice]}
    self.assertEqual(
        self.client.SuggestOwners(['a']),
        [alice])

    self.client.owners_by_path = {'abcd': [alice, bob, chris, dave]}
    self.assertEqual(
        sorted(self.client.SuggestOwners(['abcd'])),
        [alice, bob])

    self.client.owners_by_path = {
        'ae': [alice, emily],
        'be': [bob, emily],
        'ce': [chris, emily],
        'de': [dave, emily],
    }
    suggested = self.client.SuggestOwners(['ae', 'be', 'ce', 'de'])
    # emily should be selected along with anyone else.
    self.assertIn(emily, suggested)
    self.assertEqual(2, len(suggested))

    self.client.owners_by_path = {
        'ad': [alice, dave],
        'cad': [chris, alice, dave],
        'ead': [emily, alice, dave],
        'bd': [bob, dave],
    }
    self.assertEqual(
        sorted(self.client.SuggestOwners(['ad', 'cad', 'ead', 'bd'])),
        [alice, bob])

    self.client.owners_by_path = {
        'a': [alice],
        'b': [bob],
        'c': [chris],
        'ad': [alice, dave],
    }
    self.assertEqual(
        sorted(self.client.SuggestOwners(['a', 'b', 'c', 'ad'])),
        [alice, bob, chris])

    self.client.owners_by_path = {
        'abc': [alice, bob, chris],
        'acb': [alice, chris, bob],
        'bac': [bob, alice, chris],
        'bca': [bob, chris, alice],
        'cab': [chris, alice, bob],
        'cba': [chris, bob, alice]
    }
    suggested = self.client.SuggestOwners(
        ['abc', 'acb', 'bac', 'bca', 'cab', 'cba'])
    # Any two owners.
    self.assertEqual(2, len(suggested))

  def testBatchListOwners(self):
    self.client.owners_by_path = {
        'bar/everyone/foo.txt': [alice, bob],
        'bar/everyone/bar.txt': [bob],
        'bar/foo/': [bob, chris]
    }

    self.assertEquals(
        {
            'bar/everyone/foo.txt': [alice, bob],
            'bar/everyone/bar.txt': [bob],
            'bar/foo/': [bob, chris]
        },
        self.client.BatchListOwners(
            ['bar/everyone/foo.txt', 'bar/everyone/bar.txt', 'bar/foo/']))


if __name__ == '__main__':
  unittest.main()
