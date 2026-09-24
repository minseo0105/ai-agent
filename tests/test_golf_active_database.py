import json
from pathlib import Path
import unittest
from unittest.mock import patch
from services import golf_repository as repo

class ActiveDatabaseTests(unittest.TestCase):
    def test_pinned_database_ignores_checkout_timestamps(self):
        name='golf_master_precision_checkpoint_2026-09-23_filled.json'
        with patch.object(Path,'exists',return_value=True),patch.object(repo,'_read_json',return_value={'filename':name}),patch.object(repo,'_validate_db',return_value=(True,527)),patch.object(repo,'list_db_candidates',side_effect=AssertionError('must not use mtime')):
            self.assertEqual(repo.find_active_db(),repo.GOLF_DATA_DIR/name)
    def test_invalid_pin_fails_closed(self):
        for name in ['../other.json','folder\\other.json','missing_checkpoint.json']:
            with self.subTest(name=name),patch.object(Path,'exists',return_value=True),patch.object(repo,'_read_json',return_value={'filename':name}),patch.object(repo,'_validate_db',return_value=(False,0)):
                with self.assertRaises(ValueError):repo.find_active_db()
    def test_no_manifest_preserves_legacy_discovery(self):
        candidate=repo.GOLF_DATA_DIR/'golf_master_checkpoint.json'
        with patch.object(Path,'exists',return_value=False),patch.object(repo,'list_db_candidates',return_value=[candidate]),patch.object(Path,'stat') as stat:
            stat.return_value.st_mtime=10
            self.assertEqual(repo.find_active_db(),candidate)
if __name__=='__main__':unittest.main()
