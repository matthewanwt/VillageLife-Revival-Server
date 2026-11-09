import tempfile
import unittest
from pathlib import Path
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.social_store import SocialRepository


class SocialTests(unittest.TestCase):
    def test_friendships_require_recipient_acceptance(self):
        with tempfile.TemporaryDirectory() as path:
            repo = SqliteSaveRepository(Path(path) / 'data.db')
            a, b = repo.create_account('A'), repo.create_account('B')
            social = SocialRepository(repo)
            self.assertTrue(social.request_friend(a, b))
            self.assertEqual(social.friends(a), [])
            self.assertEqual(social.pending(b), [a])
            self.assertFalse(social.accept_friend(a, b))  # requester can't accept for recipient
            self.assertTrue(social.accept_friend(b, a))
            self.assertEqual(social.friends(a), [b])
            self.assertEqual(social.friends(b), [a])
            self.assertTrue(social.remove_friend(a, b))
            self.assertEqual(social.friends(b), [])


if __name__ == '__main__':
    unittest.main()
