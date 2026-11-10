import hashlib
import json
import tempfile
import unittest
from pathlib import Path


def tracks(count=3):
    return [dict(id=str(i), title=f'Song {i}', path=f'{i}.mp3',
                 sha256=hashlib.sha256(str(i).encode()).hexdigest(), bytes=1,
                 historical_usage=[]) for i in range(count)]


class RotationTests(unittest.TestCase):
    def service(self, root, songs=None):
        from pipeline.bgm import Rotation
        return Rotation(Path(root), dict(version='1.0.0', tracks=songs or tracks()), choose=lambda xs: xs[0])

    def complete(self, rotation, day):
        selected = rotation.reserve(day)
        rotation.commit(day, 'a' * 64)
        return selected

    def test_each_cycle_is_unique_and_boundary_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            r = self.service(temp)
            selected = [self.complete(r, f'2026-11-{day:02}') for day in range(1, 8)]
            self.assertEqual(len({x['track']['sha256'] for x in selected[:3]}), 3)
            self.assertEqual(len({x['track']['sha256'] for x in selected[3:6]}), 3)
            self.assertNotEqual(selected[2]['track']['sha256'], selected[3]['track']['sha256'])
            self.assertEqual([x['cycle'] for x in selected], [1,1,1,2,2,2,3])

    def test_retry_and_reexport_keep_assignment_without_consuming_another_song(self):
        with tempfile.TemporaryDirectory() as temp:
            r = self.service(temp)
            first = r.reserve('2026-11-01')
            self.assertEqual(first['track'], self.service(temp).reserve('2026-11-01')['track'])
            r.commit('2026-11-01', 'a'*64)
            self.assertEqual(first['track'], self.service(temp).reserve('2026-11-01')['track'])
            r.commit('2026-11-01', 'b'*64)
            self.assertEqual(len(r.status()['used']), 1)
            self.assertEqual(len(r.status()['assignments']), 1)

    def test_failed_pending_does_not_count_as_used(self):
        with tempfile.TemporaryDirectory() as temp:
            r = self.service(temp)
            first = r.reserve('2026-11-01')
            self.assertEqual(r.status()['used'], [])
            # No success commit: the next invocation can choose this song again.
            self.assertEqual(first['track'], r.reserve('2026-11-02')['track'])
            self.assertEqual(r.status()['cycle'], 1)

    def test_additions_join_current_cycle_and_removals_do_not_block_wrap(self):
        with tempfile.TemporaryDirectory() as temp:
            r = self.service(temp, tracks(2))
            self.complete(r,'2026-11-01')
            grown = self.service(temp, tracks(3))
            self.assertEqual(self.complete(grown,'2026-11-02')['cycle'],1)
            self.assertEqual(self.complete(grown,'2026-11-03')['cycle'],1)
            removed = self.service(temp, tracks(1))
            self.assertEqual(self.complete(removed,'2026-11-04')['cycle'],2)

    def test_historical_dates_seed_once_and_theme_is_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            songs=tracks(3)
            songs[0]['historical_usage']=['2026-11-09']
            songs[2]['historical_usage']=['approved_8_second_opening']
            songs[2]['id']='news-theme'
            r=self.service(temp,songs)
            self.assertEqual(r.reserve('2026-11-10')['track']['id'],'1')
            self.assertEqual(len(r.status()['assignments']),1)
            self.assertEqual(len(self.service(temp,songs).status()['assignments']),1)

    def test_content_duplicates_are_one_choice_and_rename_does_not_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            songs=tracks(2)
            songs.append(dict(songs[0],id='alias',path='renamed.mp3'))
            r=self.service(temp,songs)
            self.complete(r,'2026-11-01')
            self.assertEqual(r.status()['eligible_tracks'],2)
            changed=[dict(songs[0],id='renamed',path='new.mp3'),songs[1]]
            self.assertEqual(self.service(temp,changed).reserve('2026-11-02')['track']['id'],'1')

    def test_corrupt_state_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'history.json').write_text('{broken')
            with self.assertRaises(ValueError):self.service(temp).reserve('2026-11-01')

    def test_committed_old_edition_keeps_original_catalog_version(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.service(temp)
            first=self.complete(r,'2026-11-01')
            from pipeline.bgm import Rotation
            new=Rotation(Path(temp),dict(version='2.0.0',tracks=tracks(4)),choose=lambda x:x[0])
            self.assertEqual(new.reserve('2026-11-01')['catalog_version'],first['catalog_version'])

    def test_empty_pool_and_invalid_video_hash_fail_before_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            from pipeline.bgm import Rotation
            with self.assertRaises(ValueError):Rotation(Path(temp),dict(version='1.0.0',tracks=[])).reserve('2026-11-01')
            r=self.service(temp);r.reserve('2026-11-01')
            with self.assertRaises(ValueError):r.commit('2026-11-01','wrong')
            self.assertEqual(r.status()['used'],[])

    def test_new_song_prevents_failed_pending_from_starting_a_cycle_too_early(self):
        with tempfile.TemporaryDirectory() as temp:
            r=self.service(temp,tracks(2))
            self.complete(r,'2026-11-01');self.complete(r,'2026-11-02')
            self.assertEqual(r.reserve('2026-11-03')['cycle'],2)
            # The failed export was not used. A newly published song must finish
            # the current cycle before a retry is allowed to begin the next one.
            updated=self.service(temp,tracks(3))
            selected=self.complete(updated,'2026-11-03')
            self.assertEqual(selected['cycle'],1)
            self.assertEqual(selected['track']['id'],'2')

if __name__=='__main__':unittest.main()


class CacheLifecycleTests(unittest.TestCase):
    def test_cleanup_reclaims_only_owned_cache_and_keeps_history_and_originals(self):
        from pipeline.bgm import clean_cache
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);cache=root/'cache'
            clean_cache(cache)
            audio=cache/('a'*64+'.mp3');audio.write_bytes(b'download copy')
            partial=cache/('b'*64+'.ogg.part');partial.write_bytes(b'incomplete')
            original=root/'original.mp3';original.write_bytes(b'user original')
            (root/'history.json').write_text('{"keep":true}')
            receipt=clean_cache(cache)
            self.assertEqual(receipt['deleted_bytes'],len(b'download copyincomplete'))
            self.assertEqual(receipt['audio_bytes_after'],0)
            self.assertTrue(original.exists());self.assertTrue((root/'history.json').exists())

    def test_cleanup_refuses_to_adopt_user_directory(self):
        from pipeline.bgm import clean_cache
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)/'cache';cache.mkdir();(cache/'song.mp3').write_bytes(b'original')
            with self.assertRaises(ValueError):clean_cache(cache)
            self.assertEqual((cache/'song.mp3').read_bytes(),b'original')

    def test_process_lock_rejects_another_owner_and_releases_on_exception(self):
        from pipeline.bgm import music_lock
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError,'test'):
                with music_lock(temp):
                    with self.assertRaises(RuntimeError):
                        with music_lock(temp):pass
                    raise RuntimeError('test')
            with music_lock(temp):pass
